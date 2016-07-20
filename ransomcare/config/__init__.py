#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os

if os.environ.get('RANSOMECARE_ENV') == 'dev':
    from .dev import *
else:
    from .prod import *
