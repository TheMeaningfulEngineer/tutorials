This tutorial will show how to set up mender monitoring to report on a common issue:

> A critical application crashed or blocked in a restart loop

We'll examine different contexts in which this problem can occur:

* A shell spawned process
* A container 
* A systemd service

## Prerequisites

* Raspberry PI 3 or 4
* Successful completion of the [Prepare a Raspberry Pi device](https://docs.mender.io/get-started/preparation/prepare-a-raspberry-pi-device)
    * The device is live and registered in your Hosted Mender account
    * The shell of the device is accessible regardless of the method (SSH, UART, Mender Remote terminal)
    * `mender-monitorctl` is available

This tutorial is based on a CLI python app that can crash arbitrarily.

Please copy the [code for the app](#crasherpy) to a file called `crasher.py`.
Once that is ready move it on the device and make it executable:

```
# start remote terminal
# drag&drop crasher.py into it
# upload the file to /root/crasher.py
# switch to remote terminal and execute

chmod 755 crasher.py 

# Confirm it's working 
./crasher.py -h 
# Usage: crasher.py [-h] [--log-to-file] [--crash-interval SEC_BEFORE_CRASH]
# <Rest of the help text...> 
```

## Monitoring a log file

For this use case, we will monitor the application log for signs of crashing.

Run the code below to understand how the application works.

```
./crasher.py --log-to-file --crash-interval 20 --fake-crash & sleep 1; tail -f crasher.log
# Ctrl+c stops tailing crasher.log
# crasher.py keep on running in the background
```

The application prints the logs into the log file `crasher.log`
It prints `ERROR:root:Crashing...` when it crasher.
Detecting the pattern `ERROR` in the log file must trigger an alert.

To create the monitoring service to achieve this  execute:

```
#                       "Subsystem"  "Arbitrary name"  "Pattern"    "Log file"         "Duration of match validity [Optional]"
mender-monitorctl create    log         crasher_app      ERROR     /root/crasher.log                5

# The "Arbitrary name" is just a name to recognize the service.
# Internally the logging subsystem won't be mapping this to anything.
```
The [log subsystem](https://docs.mender.io/add-ons/monitor/monitoring-subsystems#log) of the monitoring service is used.

The last optional parameter is called [DEFAULT_LOG_PATTERN_EXPIRATION_SECONDS](https://docs.mender.io/add-ons/monitor/advanced-configuration#default_log_pattern_expiration_seconds). 
It represents the time that needs to pass until the pattern match is considered invalidated, given no new matches occurred in that period.
In other words, if `ERROR` is detected once and nothing happens in the next 5 seconds, monitoring will report all issues were resolved.

The command below creates the monitoring service and starts the app.

```
mender-monitorctl enable log crasher_app
```

Soon after the alerts will be visible in the UI and email alerts will be sent to the user.

To disable the alerts and the app run:
```
fg
# Ctrl+c

mender-monitorctl disable log crasher_app
mender-monitorctl delete log crasher_app
```

### Monitoring a docker container

For this use case, we will monitor the container for signs of crashing.

To install Docker on the Raspberry execute:

```
# In Remote terminal
curl -fsSL https://get.docker.com -o get-docker.sh
sh get-docker.sh
```

Move the [Dockerfile](#dockerfile) to the device.

```
# start remote terminal
# drag&drop Dockerfile into it
# upload the file to /root/Dockerfile
```

Build the container and let it run in the background

```
docker build -t crasher-docker-image .
docker run --privileged --restart on-failure --name crasher-container -d -v $(pwd):/data crasher-docker-image

# Confirm the container running and crashing
docker events
# Ctrl + c to cancel
```

To track a container we'll use a feature of the `log` subsystem.
In the first example, a file was specified as the argument.
It is also possible to monitor the output of a command by prepending it with `@` and specifying this as the "Log file" parameter.
In the example below we're creating a log service that will parse the output of `docker events` for patterns representing a dying container. 

```
#                       "Subsystem"  "Arbitrary name"                  "Pattern"                    "Log file/Command"     "Duration of match validity"
mender-monitorctl create    log      monitor-container   ".*container die.*image=crasher-docker-image"     "@docker events"                    15
mender-monitorctl enable log monitor-container
systemctl restart mender-monitor
```

Once started on the device very soon the alerts become visible in the UI notifying you about the error.


Cleanup:
```
docker restart crasher-container
sleep 5
mender-monitorctl disable log monitor-container
mender-monitorctl delete log monitor-container
docker stop crasher-container
docker rm crasher-container

# Confirm no more services running or available
docker ps
mender-monitorctl list
```


### Monitoring a systemd service


Let's turn crasher into a systemd service so it can crash for real.

Please copy the [code for the systemd unit file](#crasherservice-no-restarting) to a file called `crasher.service`.

```
# start remote terminal
# drag&drop crasher.service
# upload the file to /etc/systemd/system 
# switch to remote terminal and execute

systemctl start crasher
journalctl -fu crasher
# Ctrl + c to cancel
```

The service will never crash on its own, but we'll kill it on the device with a command.


The code below sets up a "monitoring service" to track a "systemd service":

```
#                          "Subsystem"   "Service name"   "Subsystem type"
mender-monitorctl create     service         crasher           systemd
# PLEASE NOTE
# The "Service name" must be the same as the actual systemd service. 
```

As we enable the service and track the `journalctl` together with the Hosted Mender UI,
we can see how the alert shows up once the application crashes.

```
mender-monitorctl enable service crasher
systemctl stop crasher
```

As the systemd service is stopped a notification show up in the UI.


Cleanup:
```
systemctl start crasher
sleep 5 
mender-monitorctl disable service crasher
mender-monitorctl delete service crasher
systemctl stop crasher
```


#### Flapping 101

Apps usually have mechanisms in place to auto-restart in case of a crash. 
This can fix a problem but can also leave the app in the state of a restart loop.

If we're lucky the restart loop is obvious and the app restarts every 5 seconds.
It will flood the logs but at the same time grab our attention.

However, the restart loop can happen in unequal intervals.
Restarting 3 times in an hour, making it easy to miss the issue as for the majority of the time everything is fine.

The flapping detection mechanism of mender-montioring can help with those cases.

Let's start with a definition of a flap:

> 1 flap = A state shift between running and not running and vice versa

The  configuration variables involved in flap detection:

* `FLAPPING_INTERVAL`
    * The period for which the number of flaps is being counted
* `FLAPPING_COUNT_THRESHOLD`
    * Amount of flaps which need to happen within the `FLAPPING_INTERVAL` to create a flapping alert
* `ALERT_LOG_MAX_AGE`
    * The max number of seconds for which we keep the alerts in memory for flapping detection.


#### Flapping example


Upload the new [crasher.service](#crasherservice-restarting) to `/etc/systemd/system`.
When started the systemd service will run for a random period in the range of 50-60 seconds and take 10 seconds to restart.

```
# Conceptual representation, not output logs
[50-60] sec running
10 sec crashed
[50-60] sec running
10 sec crashed
...
```

The below code will change the configuration values to trigger a flapping alert as soon as there are 3 flaps in 120 seconds.

```
sed -i 's/FLAPPING_INTERVAL=.*/FLAPPING_INTERVAL=150/g' /usr/share/mender-monitor/config/config.sh
sed -i 's/FLAPPING_COUNT_THRESHOLD=.*/FLAPPING_COUNT_THRESHOLD=3/g' /usr/share/mender-monitor/config/config.sh
```

The same monitoring service from the previous example is used:

```
mender-monitorctl create service crasher systemd
systemctl start crasher
mender-monitorctl enable service crasher
```

As we start both services and track the Hosted Mender UI, the first that shows up are notifications of a crashed application followed by a notification of the application running again.


Cleanup:
```
systemctl restart crasher
sleep 10
mender-monitorctl disable service crasher
mender-monitorctl delete service crasher
systemctl stop crasher
```


## Code references

### Dockerfile

[Back](#monitoring-a-docker-container)

```
FROM python:3.9
CMD [ "./data/crasher.py", "--crash-interval", "30"]
```

### crasher.service [no restarting]

[Back](#monitoring-a-systemd-service)

```
[Unit]
Description=Crasher
After=network.target

[Service]
Type=simple
ExecStart=/root/crasher.py --never-crash

[Install]
WantedBy=multi-user.target
```

### crasher.service [restarting]

[Back](#flapping-example)

```
[Unit]
Description=Crasher
After=network.target

[Service]
Type=simple
Restart=always
RestartSec=10
ExecStart=/root/crasher.py --crash-interval-random 50 60

[Install]
WantedBy=multi-user.target
```

### crasher.py

[Back](#prerequisites)

```
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
```
