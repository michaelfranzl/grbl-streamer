Gerbil -- Universal grbl interface module for Python3
=======================================================

Universal interface module for the grbl CNC firmware (see https://github.com/grbl/grbl) written for Python3. It provides a convenient high-level API for scripting or integration into parent applications like GUI's.

There are a number of streaming applications available for the grbl CNC controller, but none of them seem to be an universal, re-usable standard Python module. Gerbil attempts to fill that gap.

Gerbil is a name of a cute desert rodent. It is chosen due to its similarity to the name "grbl", of which probably nobody knows what it means ;)

    
Features
--------

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

Documentation
--------

I believe that the code is well documented. This module is for developers for integration into parent applications, not end users.


Usage example
--------

Make work directory::

    mkdir ~/work
    cd ~/work

Get sources::

    git clone git@github.com:michaelfranzl/gerbil.git
    git clone git@github.com:michaelfranzl/gcode_machine.git

Go into a Python3 console::

    python3

... and import the class Gerbil::

    from gerbil.gerbil import Gerbil
    
Next, copy-paste the following code into the console. This is your callback function that Gerbil will call asynchronously whenever an event happens. The following example function does nothing else than logging to stdout. In a real GUI application, you would update numbers, sliders etc. from this function::

    def my_callback(eventstring, *data):
        args = []
        for d in data:
            args.append(str(d))
        print("MY CALLBACK: event={} data={}".format(eventstring.ljust(30), ", ".join(args)))
        # Now, do something interesting with these callbacks
    
Next, instantiate an instance of the Gerbil class::

    grbl = Gerbil(my_callback)
    
Next, we tell Gerbil to use its default log handler, which, instead of printing to stdout directly, will also call above `my_callback` function with eventstring `on_log`. You could use this, for example, to output the logging strings in a GUI window::

    grbl.setup_logging()
    
We now can connect to the grbl firmware, the actual CNC machine::

    grbl.cnect("/dev/ttyUSB0", 57600) # or /dev/ttyACM0
    
We will poll every half second for the state of the CNC machine (working position, etc.)::

    grbl.poll_start()
    
Now, we'll send our first G-Code command. When you'll see the callback function called with `evenstring` set to "on_stateupdate", you'll know that your command is executed, and you'll see the X, Y and Z coordinates updating. (Warning, if you're connected to a CNC machine, it will move at this point!!)::

    grbl.send_immediately("G0 X200")
    
Now let's send the `$#` command to the firmware, so that it reports back coordinate system offset information::

    grbl.hash_state_requested = True
    
Note that all of the payload data sent to `my_callback` are already parsed out for easier consumption! Here, for just one example, is what above function `my_callback` will print out at this point::

    MY CALLBACK: event=on_hash_stateupdate            data={'G58': (-14.996, 0.0, 6.0), 'G56': (15.994, 6.999, 0.0), 'TLO': (0.0,), 'G92': (0.0, 0.0, 0.0), 'G59': (28.994, 38.002, 6.0), 'G28': (0.0, 0.0, 0.0), 'G54': (-99.995, -99.995, 0.0), 'G55': (-400.005, -400.005, 0.0), 'PRB': (0.0, 0.0, 0.0), 'G57': (10.0, 10.0, 10.0), 'G30': (0.0, 0.0, 0.0)}
    
You could simply access the offset of the G55 coordinate system in above function with::

    >>> data["G55"]
    (-400.005, -400.005, 0.0)

Next, let's requst the firmware G-code parser state (grbl's `$G` command)::
    
    grbl.gcode_parser_state_requested = True
    
We also can request the settings (grbl's `$$` command)::

    grbl.request_settings()

Gerbil supports dynamic feed override. You could have a slider in your GUI controlling the milling speed of your machine as it runs::

    grbl.set_feed_override(True)
    grbl.request_feed(800)
    grbl.stream("F100 G1 X210 \n G1 X200 \n G1 Y210 \n G1 Y200 \n")

When we're done, we disconnect from the firmware::

    grbl.disconnect()


TODO
-------

* Make this project more compliant with Python module packaging.

    
License
--------

Gerbil (c) 2015 Michael Franzl

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
