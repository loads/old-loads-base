import logging
import os

logger = logging.getLogger('loads')


def set_logger(debug=False, name='loads', logfile='stdout'):
    # setting up the logger
    logger_ = logging.getLogger(name)
    logger_.setLevel(logging.DEBUG)

    if logfile == 'stdout':
        ch = logging.StreamHandler()
    else:
        ch = logging.handlers.RotatingFileHandler(logfile, mode='a+')

    if debug:
        ch.setLevel(logging.DEBUG)
    else:
        ch.setLevel(logging.INFO)

    formatter = logging.Formatter('[%(asctime)s][%(process)d] %(message)s')
    ch.setFormatter(formatter)
    logger_.addHandler(ch)

    # for the tests
    if 'TESTING' in os.environ:
        fh = logging.FileHandler('/tmp/loads.log')
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(formatter)
        logger.addHandler(fh)
