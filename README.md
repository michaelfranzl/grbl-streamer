# Gerbil -- Universal grbl interface module for Python3

Universal interface module written in Python 3 for the [grbl](https://github.com/grbl/grbl) CNC firmware. It provides a convenient high-level API for scripting or integration into parent applications like GUI's.

There are a number of streaming applications available for the grbl CNC controller, but none of them seem to be an universal, re-usable standard Python module. Gerbil attempts to fill that gap.

Gerbil is a name of a cute desert rodent. It is chosen due to its similarity to the name "grbl", of which probably nobody knows what it means ;)


## Features

* Re-usable across projects
* Non-blocking
* Asynchronous (event-based) callbacks for the parent application
* Two streaming modes: Incremental or fast ("counting characters")
* Defined shutdown
* G-Code cleanup
* G-Code variable expansion
* Dynamic feed override
* Buffer stashing
* Job halt and resume


## Installation

```sh
python -m pip install gerbil
```


## Usage

```python
from gerbil import Gerbil
```

Define a callback function that Gerbil will call asynchronously whenever some event happens.
The following example function does nothing else than logging to stdout.
In a real GUI application, you would update numbers, sliders etc. from this function:

```python
def my_callback(eventstring, *data):
    args = []
    for d in data:
        args.append(str(d))
    print("MY CALLBACK: event={} data={}".format(eventstring.ljust(30), ", ".join(args)))
```

Instantiate an instance of the Gerbil class::

```python
grbl = Gerbil(my_callback)
```

Tell Gerbil to use its default log handler, which, instead of printing to stdout directly, will also call above `my_callback` function with eventstring `on_log`. You could use this, for example, to output the logging strings in a GUI window:

```python
grbl.setup_logging()
```

We now can connect to the grbl firmware, the actual CNC machine::

```python
grbl.cnect("/dev/ttyUSB0", 57600) # or /dev/ttyACM0
```

We will poll every half second for the state of the CNC machine (working position, etc.)::

```python
grbl.poll_start()
```

Now, we'll send our first G-Code command. When you'll see the callback function called with `evenstring` set to "on_stateupdate", you'll know that your command is executed, and you'll see the X, Y and Z coordinates updating. (Warning, if you're connected to a CNC machine, it will move at this point!!)::

```python
grbl.send_immediately("G0 X200")
```

Now let's send the `$#` command to the firmware, so that it reports back coordinate system offset information::

```python
grbl.hash_state_requested = True
```

Note that all of the payload data sent to `my_callback` are already parsed out for easier consumption! Here, for just one example, is what above function `my_callback` will print out at this point::

```
MY CALLBACK: event=on_hash_stateupdate            data={'G58': (-14.996, 0.0, 6.0), 'G56': (15.994, 6.999, 0.0), 'TLO': (0.0,), 'G92': (0.0, 0.0, 0.0), 'G59': (28.994, 38.002, 6.0), 'G28': (0.0, 0.0, 0.0), 'G54': (-99.995, -99.995, 0.0), 'G55': (-400.005, -400.005, 0.0), 'PRB': (0.0, 0.0, 0.0), 'G57': (10.0, 10.0, 10.0), 'G30': (0.0, 0.0, 0.0)}
```

You could simply access the offset of the G55 coordinate system in above function with::

```python
>>> data["G55"]
(-400.005, -400.005, 0.0)
```

Next, let's request the firmware G-code parser state (grbl's `$G` command)::

```python
grbl.gcode_parser_state_requested = True
```

We also can request the settings (grbl's `$$` command)::

```python
grbl.request_settings()
```

Gerbil supports dynamic feed override. You could have a slider in your GUI controlling the milling speed of your machine as it runs::

```python
grbl.set_feed_override(True)
grbl.request_feed(800)
grbl.stream("F100 G1 X210 \n G1 X200 \n G1 Y210 \n G1 Y200 \n")
```

When we're done, we disconnect from the firmware::

```python
grbl.disconnect()
```


# TODO

* Make this project more compliant with Python module packaging.
