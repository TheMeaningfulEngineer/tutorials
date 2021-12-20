#!/usr/bin/env python3
import argparse
import time
import sys
import logging
import random


def init_cli(log_file):
    cli = argparse.ArgumentParser(description='A app which crashes')

    interval_group = cli.add_mutually_exclusive_group()
    interval_group.add_argument('--crash-interval-random', nargs=2, type=int, default=False,
                                metavar=("Min", "Max"), help='Randomize the crash-interval')

    interval_group.add_argument('--crash-interval', type=int, default=5, metavar=("Duration"),
                                help='Duration of successful execution before the crash [Sec]')

    cli.add_argument('--log-to-file', action='store_true', default=False,
                     help=f'Outputs the logs to {log_file} instead of stderr')
    cli.add_argument('--fake-crash', action='store_true', default=False,
                     help='Print the logs as if crash happened, but keep on going')

    cli.add_argument('--never-crash', action='store_true', default=False,
                     help='Run forever and never crash')

    cli_args = cli.parse_args()

    if cli_args.crash_interval_random:
        cli_args.crash_interval = False

    return cli_args


def setup_logging(log_to_file, log_file):
    if log_to_file:
        logging.basicConfig(filename=log_file, filemode='a', level=logging.INFO)
        logging.info(f"Logging to file {log_file}")
    else:
        logging.basicConfig(level=logging.INFO)


def init_timer(cli_args):
    if cli_args.crash_interval_random:
        duration_min, duration_max = cli_args.crash_interval_random[0], cli_args.crash_interval_random[1]
        if duration_min > duration_max:
            logging.error("Minimum duration must be smaller then maximum")
            sys.exit(1)

        logging.info(f"Random crash interval [{duration_min}-{duration_max}]")
        timer_fixed = random.randint(duration_min, duration_max)
    else:
        timer_fixed = cli_args.crash_interval
    return timer_fixed


def never_crash():
    logging.info("I will never crash")
    while True:
        time.sleep(1)
        continue


if __name__ == "__main__":
    log_file = "crasher.log"
    cli_args = init_cli(log_file)
    setup_logging(cli_args.log_to_file, log_file)

    if cli_args.never_crash:
        never_crash()

    timer_dyn = init_timer(cli_args)
    while True:
        if timer_dyn == 0:
            logging.error("Crashing...")
            if cli_args.fake_crash:
                logging.info("Crash faked. Restarting")
                timer_dyn = init_timer(cli_args)
                time.sleep(5)
                continue
            sys.exit(1)

        logging.info(f"Crashing in {timer_dyn}")
        time.sleep(1)
        timer_dyn -= 1

