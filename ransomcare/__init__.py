#!/usr/bin/env python
# -*- coding: utf-8 -*-

__author__ = 'Yu-Cheng (Henry) Huang'

import logging

logger = logging.getLogger(__name__)

import platform
import signal
import sys

from . import user_interfaces
from . import handlers
from . import sniffers
from . import event
from . import engine


def _init_logging(level, log_stream=True, log_file=None):
    logger.setLevel(level)
    fmt = logging.Formatter('%(asctime)s %(name)s %(levelname)s: %(message)s')

    if log_stream:
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(fmt)
        stream_handler.setLevel(level)
        logger.addHandler(stream_handler)

    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(fmt)
        file_handler.setLevel(level)
        logger.addHandler(file_handler)


def main(log_level=logging.DEBUG, log_stream=True, log_file=None):
    _init_logging(level=log_level, log_stream=log_stream, log_file=log_file)

    system = platform.platform().lower()
    if system.startswith('darwin'):
        sniffer = sniffers.DTraceSniffer()
    else:
        raise NotImplementedError('Ransomcare is not ready for %s, '
                                  'please help porting it!' % system)

    white_list_handler = handlers.WhiteListHandler()  # handles ransom events
    event.register_event_handler(
        event.EventCryptoRansom, white_list_handler.on_crypto_ransom)
    event.register_event_handler(
        event.EventUserAllowProcess, white_list_handler.on_user_allow_process)
    event.register_event_handler(
        event.EventUserDenyProcess, white_list_handler.on_user_deny_process)

    console_ui = user_interfaces.ConsoleUI()  # user responses -> handler
    event.register_event_handler(
        event.EventAskUserAllowOrDeny, console_ui.on_ask_user_allow_or_deny)

    brain = engine.Engine()  # generates user events -> UI
    event.register_event_handler(
        event.EventFileOpen, brain.on_file_open)
    event.register_event_handler(
        event.EventListDir, brain.on_list_dir)
    event.register_event_handler(
        event.EventFileRead, brain.on_file_read)
    event.register_event_handler(
        event.EventFileWrite, brain.on_file_write)
    event.register_event_handler(
        event.EventFileUnlink, brain.on_file_unlink)
    event.register_event_handler(
        event.EventFileClose, brain.on_file_close)

    brain_cleaner_thread = brain.start_cleaner()

    web_ui = user_interfaces.WebUI(engine=brain)
    web_ui_thread = web_ui.start()
    event.register_event_handler(
        event.EventCryptoRansom, web_ui.on_crypto_ransom)

    ctx = {}
    def clean_up(*args, **kwargs):
        logger.debug('Cleaning up everything...')
        sniffer.stop()
        web_ui.stop()
        brain.stop_cleaner()

        web_ui_thread.join()
        brain_cleaner_thread.join()
        ctx['cleaned_up'] = True

    signal.signal(signal.SIGINT, clean_up)

    sniffer.start()  # generates file events -> brain

    if not ctx.get('cleaned_up'):
        clean_up()
