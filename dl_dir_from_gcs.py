__author__ = "Richard Correro (richard@richardcorrero.com)"


import argparse
import hashlib
import os
import random
import time

from script_utils import get_args

SCRIPT_PATH = os.path.basename(__file__)

SECRET_KEY = 'f39sj)3j09ja0e8f1as98u!98auf-b23bacxmza9820h35m./9'

try:
    random = random.SystemRandom()
    using_sysrandom = True
except NotImplementedError:
    import warnings
    warnings.warn('A secure pseudo-random number generator is not available '
                  'on your system. Falling back to Mersenne Twister.')
    using_sysrandom = False


def get_random_string(length=12,
                      allowed_chars='abcdefghijklmnopqrstuvwxyz'
                                    'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'):
    """
    Returns a securely generated random string.

    The default length of 12 with the a-z, A-Z, 0-9 character set returns
    a 71-bit value. log_2((26+26+10)^12) =~ 71 bits
    """
    if not using_sysrandom:
        # This is ugly, and a hack, but it makes things better than
        # the alternative of predictability. This re-seeds the PRNG
        # using a value that is hard for an attacker to predict, every
        # time a random string is required. This may change the
        # properties of the chosen random sequence slightly, but this
        # is better than absolute predictability.
        random.seed(
            hashlib.sha256(
                ("%s%s%s" % (
                    random.getstate(),
                    time.time(),
                    SECRET_KEY)).encode('utf-8')
            ).digest())
    return ''.join(random.choice(allowed_chars) for i in range(length))


def main():
    parser = argparse.ArgumentParser(
        description="Download directory from Google Cloud Storage."
    )
    parser.add_argument('--bucket', type=str, required=True)
    parser.add_argument('--remote-dir', type=str, required=True)
    parser.add_argument('--local-dir', type=str, required=True)
    parser.add_argument('--gcs-credentials', type=str, required=True)


    args, _ = parser.parse_known_args()
    args = vars(args)

    args = get_args(script_path=SCRIPT_PATH, **args)
    


if __name__ == "__main__":
    main()