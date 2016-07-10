#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import subprocess
import json
import logging

import psutil

from . import event

logger = logging.getLogger(__name__)
pid_cwd = {}


def get_absolute_path(event_raw):
    '''
    Keeps a cache of processes' cwds, in case that their events might come
    after they're terminated.
    '''
    pid = event_raw.get('pid')
    fd = event_raw.get('fd')
    path = event_raw.get('path')
    if path and path[0] == '/':
        return path

    cwd = None
    logger.debug('%r' % pid_cwd)
    try:
        process = psutil.Process(pid)
        cwd = process.cwd()
        pid_cwd[pid] = cwd  # cache every pid's cwd
    except psutil.NoSuchProcess:
        cwd = pid_cwd.get(pid)
        if not cwd:
            return None

    return os.path.abspath(os.path.join(cwd, path))


class DTraceSniffer(object):
    '''
    Sniffs and generates file events:
        EventFileOpen (pid, path)
        EventListDir (pid, path)
        EventFileRead (pid, path, size)
        EventFileWrite (pid, path, size)
        EventFileUnlink (pid, path)
        EventFileClose (pid, path)

    The path generated from dtrace might be relative paths, sniffer is
    reponsible for translating them into absolute paths.
    '''
    def __init__(self):
        self.sniffer = None
        self.stop = False

    def start(self):
        DEVNULL = open(os.devnull, 'wb')
        logger.debug('Excluding self: %d' % os.getpid())
        self.sniffer = subprocess.Popen(
            ['./ransomcare/sniffer', '-x', str(os.getpid()), '-n', 'Python'],
            stdout=subprocess.PIPE, stderr=DEVNULL)

        while not self.stop:
            try:
                line = self.sniffer.stdout.readline()
                event_raw = json.loads(line)
            except ValueError:
                logger.warn('Failed to JSON-decode: "%r"' % line)
                continue
            action = event_raw.get('action')
            pid = event_raw.get('pid')
            path = get_absolute_path(event_raw)  # returns None if file closed
            if path is None:
                continue  # ignore closed files
            size = event_raw.get('size')
            timestamp = event_raw.get('t')
            if action == 'open':
                event.dispatch(event.EventFileOpen(timestamp, pid, path))
            elif action == 'listdir':
                event.dispatch(event.EventListDir(timestamp, pid, path))
            elif action == 'read':
                event.dispatch(event.EventFileRead(timestamp, pid, path, size))
            elif action == 'write':
                event.dispatch(
                    event.EventFileWrite(timestamp, pid, path, size))
            elif action == 'close':
                event.dispatch(event.EventFileClose(timestamp, pid, path))
            elif action == 'unlink':
                event.dispatch(event.EventFileUnlink(timestamp, pid, path))
        DEVNULL.close()