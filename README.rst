Gerbil -- A universal Grbl interface module for Python3
=======================================================

A universal Grbl CNC firmware interface module for Python3 providing a convenient high-level API for scripting or integration into parent applications like GUI's.

There are a number of streaming applications available for the Grbl CNC controller, but none of them seem to be an universal, re-usable standard Python module. Gerbil attempts to fill that gap.

Gerbil is a name of a cute desert rodent. We chose the name due to its similarity to the name "Grbl".

    
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

## Documentation

We believe that the code is well documented. This module is for developers, not end users.

## Usage example

from gerbil import Gerbil

def my_callback(eventstring, *data):
    args = []
    for d in data:
        args.append(str(d))
    print("MY CALLBACK: event={} data={}".format(eventstring.ljust(30), ", ".join(args)))
    # Now, do something interesting with these callbacks

grbl = Gerbil()
grbl.setup_logging()
grbl.callback = my_callback
grbl.cnect()
grbl.poll_start()

grbl.send_immediately("G0 X200")

grbl.hash_state_requested = True
grbl.gcode_parser_state_requested = True

grbl.request_settings()

grbl.send_with_queue("G0 X10 \n G0 X0 \n G0 Y10 \n G0 Y0 \n")


grbl.disconnect()


# License

"Gerbil" (c) 2015 Red (E) Tools Ltd.

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.