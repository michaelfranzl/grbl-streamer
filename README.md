# GrblStreamer

Universal interface module for the [grbl](https://github.com/grbl/grbl) CNC firmware, implemented as a Python 3 class.
It provides a convenient high-level API for scripting or integration into parent applications (e.g. GUIs).

There are a number of streaming applications available for the grbl CNC controller, but none of them seem to be an universal, re-usable standard Python module. GrblStreamer attempts to fill that gap.


## Features

* Re-usable module
* Callback based
   * grbl's machine position updates
   * grbl's probe events (PRB)
   * grbl's alarm events (ALARM)
   * grbl's errors
   * grbl's booting
   * grbl's settings updates
   * grbl's g-code parser state updates
   * log lines
* keeps a copy of grbl's state for immediate inspection
* Non-blocking streaming of g-code
* Two streaming modes:
   * Incremental
   * fast (keep grbl's receive buffer as full as possibly by keeping track of submitted characters)
* Streaming from files or Python lists
* Keeps track of the fill percentage of grbl's receive buffer
* Requesting of grbl's settings
* Requesting of grbl's parser state ('G' modes)
* Dry run (simulator) mode
* g-code buffer stashing
* pausing and resuming of the g-code stream
* controlled shutdown

The following features are also available, coming from my library [gcode-machine](https://github.com/michaelfranzl/gcode_machine):

* G-Code compression by cleaning it up
* G-Code variable expansion
* Dynamic feed override
* Dynamic spindle override


## Integration example

See GrblStreamer integrated with its full feature set in a graphical user interface based on Python 3 with Qt5 bindings: https://github.com/michaelfranzl/gerbil_gui.


## Installation

```sh
pip install grbl-streamer
```

## Documentation

The module is only about 1300 lines of code, which is extensively documented.


## Getting started

```python
from grbl_streamer import GrblStreamer
```

Define a callback function that GrblStreamer will call asynchronously whenever some event happens.
The following example function does nothing else than logging to standard output.
In a real GUI application, you would update numbers, sliders etc. from this method.

```python
def my_callback(eventstring, *data):
    args = []
    for d in data:
        args.append(str(d))
    print("MY CALLBACK: event={} data={}".format(eventstring.ljust(30), ", ".join(args)))
```

Here, for just one example, is what above function `my_callback` will print out at this point:

Instantiate the GrblStreamer class:

```python
grbl = GrblStreamer(my_callback)
grbl.setup_logging()
```

We now can connect to the grbl firmware, the actual CNC machine (adapt path and baudrate):

```python
grbl.cnect("/dev/ttyUSB0", 115200)
```

This will emit the events `on_boot`, `on_settings_downloaded` and others.

We will poll every half second for the state of the CNC machine (working position, etc.):

```python
grbl.poll_start()
```

Now, we'll send our first G-Code command.
This will emit events like `on_movement`, `on_stateupdate`, `on_standstill` and others.


```python
grbl.send_immediately("G1 X5 F50")
```

Now let's send the `$#` command to the firmware, so that it reports back coordinate system offset information. The event `on_hash_stateupdate` will be emitted:

```python
grbl.hash_state_requested = True
```

Example result:

```
MY CALLBACK: event=on_hash_stateupdate            data={'G54': (0.0, 0.0, 0.0), 'G55': (0.0, 0.0, 0.0), 'G56': (0.0, 0.0, 0.0), 'G57': (0.0, 0.0, 0.0), 'G58': (0.0, 0.0, 0.0), 'G59': (0.0, 0.0, 0.0), 'G28': (0.0, 0.0, 0.0), 'G30': (0.0, 0.0, 0.0), 'G92': (0.0, 0.0, 0.0), 'TLO': (0.0,), 'PRB': (0.0, 0.0, 0.0)}
```

Next, let's request the firmware G-code parser state (grbl's `$G` command):

```python
grbl.gcode_parser_state_requested = True
```

Example result:

```
MY CALLBACK: event=on_gcode_parser_stateupdate    data=['1', '54', '17', '21', '90', '94', '0', '5', '9', '0', '50.', '0.']
```

We also can request the settings (grbl's `$$` command), the result will be a dict:

```python
grbl.request_settings()
```

GrblStreamer supports dynamic feed override. You could have a slider in your GUI controlling the milling speed of your machine as it runs:

```python
grbl.set_feed_override(True)
grbl.request_feed(800)
grbl.stream("F100 G1 X210 \n G1 X200 \n G1 Y210 \n G1 Y200 \n")
```

When we're done, we disconnect from the firmware:

```python
grbl.disconnect()
```


## Testing

One log file says more than a thousand words. The following is a printout of running `pipenv run make test` against a real microcontroller with grbl 0.9j:


```
        on_settings_downloaded: ({130: {'val': '1000', 'cmt': 'width'}, 131: {'val': '1000', 'cmt': 'height'}},)
           on_hash_stateupdate: ({'G54': (0, 0, 0), 'G55': (0, 0, 0), 'G56': (0, 0, 0), 'G57': (0, 0, 0), 'G58': (0, 0, 0), 'G59': (0, 0, 0), 'G28': (0, 0, 0), 'G30': (0, 0, 0), 'G92': (0, 0, 0), 'TLO': 0, 'PRB': (0, 0, 0)},)
   on_gcode_parser_stateupdate: (['0', '54', '17', '21', '90', '94', '0', '0', '5', '0', '99', '0'],)
                        on_log: mygrbl: Setting up interface on /dev/ttyUSB0
                        on_log: iface_mygrbl: connecting to /dev/ttyUSB0 with baudrate 115200
                       on_read: ("Grbl 0.9j ['$' for help]",)
              on_job_completed: ()
                on_feed_change: (None,)
           on_progress_percent: (0,)
          on_rx_buffer_percent: (0,)
                        on_log: mygrbl: Grbl has booted!
                       on_boot: ()
                      on_write: ('$$\n',)
                       on_read: ('$0=10 (step pulse, usec)',)
                       on_read: ('$1=25 (step idle delay, msec)',)
                       on_read: ('$2=0 (step port invert mask:00000000)',)
                       on_read: ('$3=0 (dir port invert mask:00000000)',)
                       on_read: ('$4=0 (step enable invert, bool)',)
                       on_read: ('$5=0 (limit pins invert, bool)',)
                       on_read: ('$6=0 (probe pin invert, bool)',)
                       on_read: ('$10=3 (status report mask:00000011)',)
                       on_read: ('$11=0.010 (junction deviation, mm)',)
                       on_read: ('$12=0.002 (arc tolerance, mm)',)
                       on_read: ('$13=0 (report inches, bool)',)
                       on_read: ('$20=0 (soft limits, bool)',)
                       on_read: ('$21=0 (hard limits, bool)',)
                       on_read: ('$22=0 (homing cycle, bool)',)
                       on_read: ('$23=0 (homing dir invert mask:00000000)',)
                       on_read: ('$24=25.000 (homing feed, mm/min)',)
                       on_read: ('$25=500.000 (homing seek, mm/min)',)
                       on_read: ('$26=250 (homing debounce, msec)',)
                       on_read: ('$27=1.000 (homing pull-off, mm)',)
                       on_read: ('$100=250.000 (x, step/mm)',)
                       on_read: ('$101=250.000 (y, step/mm)',)
                       on_read: ('$102=250.000 (z, step/mm)',)
                       on_read: ('$110=500.000 (x max rate, mm/min)',)
                       on_read: ('$111=500.000 (y max rate, mm/min)',)
                       on_read: ('$112=500.000 (z max rate, mm/min)',)
                       on_read: ('$120=10.000 (x accel, mm/sec^2)',)
                       on_read: ('$121=10.000 (y accel, mm/sec^2)',)
                       on_read: ('$122=10.000 (z accel, mm/sec^2)',)
                       on_read: ('$130=200.000 (x max travel, mm)',)
                       on_read: ('$131=200.000 (y max travel, mm)',)
                       on_read: ('$132=200.000 (z max travel, mm)',)
        on_settings_downloaded: ({130: {'val': '200.000', 'cmt': 'x max travel, mm'}, 131: {'val': '200.000', 'cmt': 'y max travel, mm'}, 0: {'val': '10', 'cmt': 'step pulse, usec'}, 1: {'val': '25', 'cmt': 'step idle delay, msec'}, 2: {'val': '0', 'cmt': 'step port invert mask:00000000'}, 3: {'val': '0', 'cmt': 'dir port invert mask:00000000'}, 4: {'val': '0', 'cmt': 'step enable invert, bool'}, 5: {'val': '0', 'cmt': 'l
imit pins invert, bool'}, 6: {'val': '0', 'cmt': 'probe pin invert, bool'}, 10: {'val': '3', 'cmt': 'status report mask:00000011'}, 11: {'val': '0.010', 'cmt': 'junction deviation, mm'}, 12: {'val': '0.002', 'cmt': 'arc tolerance, mm'}, 13: {'val': '0', 'cmt': 'report inches, bool'}, 20: {'val': '0', 'cmt': 'soft limits, bool'}, 21: {'val': '0', 'cmt': 'hard limits, bool'}, 22: {'val': '0', 'cmt': 'homing cycle, bool'}, 2
3: {'val': '0', 'cmt': 'homing dir invert mask:00000000'}, 24: {'val': '25.000', 'cmt': 'homing feed, mm/min'}, 25: {'val': '500.000', 'cmt': 'homing seek, mm/min'}, 26: {'val': '250', 'cmt': 'homing debounce, msec'}, 27: {'val': '1.000', 'cmt': 'homing pull-off, mm'}, 100: {'val': '250.000', 'cmt': 'x, step/mm'}, 101: {'val': '250.000', 'cmt': 'y, step/mm'}, 102: {'val': '250.000', 'cmt': 'z, step/mm'}, 110: {'val': '500
.000', 'cmt': 'x max rate, mm/min'}, 111: {'val': '500.000', 'cmt': 'y max rate, mm/min'}, 112: {'val': '500.000', 'cmt': 'z max rate, mm/min'}, 120: {'val': '10.000', 'cmt': 'x accel, mm/sec^2'}, 121: {'val': '10.000', 'cmt': 'y accel, mm/sec^2'}, 122: {'val': '10.000', 'cmt': 'z accel, mm/sec^2'}, 132: {'val': '200.000', 'cmt': 'z max travel, mm'}},)
          on_rx_buffer_percent: (0,)
                      on_write: ('$#\n',)
                        on_log: mygrbl: Polling thread started
             on_bufsize_change: (2,)
                on_vars_change: ({},)
           on_progress_percent: (0,)
                      on_write: ('G00Y3\n',)
                  on_line_sent: (1, 'G00Y3')
           on_progress_percent: (50,)
                      on_write: ('\n',)
                  on_line_sent: (2, '')
           on_progress_percent: (100,)
                       on_read: ('[G54:0.000,0.000,0.000]',)
                       on_read: ('[G55:0.000,0.000,0.000]',)
                       on_read: ('[G56:0.000,0.000,0.000]',)
                       on_read: ('[G57:0.000,0.000,0.000]',)
                       on_read: ('[G58:0.000,0.000,0.000]',)
                       on_read: ('[G59:0.000,0.000,0.000]',)
                       on_read: ('[G28:0.000,0.000,0.000]',)
                       on_read: ('[G30:0.000,0.000,0.000]',)
                       on_read: ('[G92:0.000,0.000,0.000]',)
                       on_read: ('[TLO:0.000]',)
                       on_read: ('[PRB:0.000,0.000,0.000:0]',)
           on_hash_stateupdate: ({'G54': (0.0, 0.0, 0.0), 'G55': (0.0, 0.0, 0.0), 'G56': (0.0, 0.0, 0.0), 'G57': (0.0, 0.0, 0.0), 'G58': (0.0, 0.0, 0.0), 'G59': (0.0, 0.0, 0.0), 'G28': (0.0, 0.0, 0.0), 'G30': (0.0, 0.0, 0.0), 'G92': (0.0, 0.0, 0.0), 'TLO': (0.0,), 'PRB': (0.0, 0.0, 0.0)},)
          on_processed_command: (0, 'G00Y3')
          on_rx_buffer_percent: (0,)
          on_processed_command: (1, '')
              on_job_completed: ()
          on_rx_buffer_percent: (0,)
          on_rx_buffer_percent: (0,)
                      on_write: ('$G\n',)
   on_gcode_parser_stateupdate: (['0', '54', '17', '21', '90', '94', '0', '5', '9', '0', '0.', '0.'],)
                       on_read: ('[G0 G54 G17 G21 G90 G94 M0 M5 M9 T0 F0. S0.]',)
          on_rx_buffer_percent: (0,)
                on_stateupdate: ('Run', (0.0, 0.724, 0.0), (0.0, 0.724, 0.0))
                on_stateupdate: ('Run', (0.0, 1.676, 0.0), (0.0, 1.676, 0.0))
                on_stateupdate: ('Run', (0.0, 2.508, 0.0), (0.0, 2.508, 0.0))
                on_stateupdate: ('Run', (0.0, 2.936, 0.0), (0.0, 2.936, 0.0))
                on_stateupdate: ('Idle', (0.0, 3.0, 0.0), (0.0, 3.0, 0.0))
                      on_write: ('$G\n',)
   on_gcode_parser_stateupdate: (['0', '54', '17', '21', '90', '94', '0', '5', '9', '0', '0.', '0.'],)
                       on_read: ('[G0 G54 G17 G21 G90 G94 M0 M5 M9 T0 F0. S0.]',)
          on_rx_buffer_percent: (0,)
.                        on_log: mygrbl: Please wait until polling thread has joined...
                        on_log: mygrbl: Polling has been stopped
                        on_log: mygrbl: Polling thread has successfully  joined...
                        on_log: iface_mygrbl: stop()
                        on_log: iface_mygrbl: JOINED thread
                        on_log: iface_mygrbl: Closing port
                        on_log: mygrbl: Please wait until reading thread has joined...
                       on_read: ('dummy_msg_for_joining_thread',)
                        on_log: mygrbl: Reading thread successfully joined.
               on_disconnected: ()

----------------------------------------------------------------------
Ran 1 test in 6.830s

OK
```


## Development

Install the Python version specified in the file `.python-version`.

Dependencies are managed using `pipenv`:

```sh
pip install pipenv --user
pipenv install --dev
```


### Building

```sh
pipenv run make dist
```
