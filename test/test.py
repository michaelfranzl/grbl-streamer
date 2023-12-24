import unittest
import time

from gerbil import Gerbil


# Run the tests against a real grbl on /dev/ttyUSB0 with 115200 baud.
# Both of the two main grbl variants should work:
#
# grbl 0.9j from
# https://github.com/grbl/grbl commit 9180094b72821ce68e33fdd779278a533a7bf40c
#
# grbl 1.1h from
# https://github.com/gnea/grbl commit bfb67f0c7963fe3ce4aaf8a97f9009ea5a8db36e
# with $10=1
#
# TODO: Write more tests. 
class Test(unittest.TestCase):
    grbl = None

    cmode = None
    cmpos = None
    cwpos = None

    @classmethod
    def callback(cls, event, *args):
        match event:
            case 'on_stateupdate':
                cls.cmode = args[0]
                cls.cmpos = args[1]

    @classmethod
    def setUpClass(cls):
        cls.grbl = Gerbil(cls.callback)
        cls.grbl.cnect('/dev/ttyUSB0', 115200)
        time.sleep(3)  # TODO: Make this more robust
        cls.grbl.poll_start()

    @classmethod
    def tearDownClass(cls):
        cls.grbl.disconnect()

    def test(self):
        Test.grbl.stream('G0 Y3\n')
        time.sleep(3)  # TODO: Make this more robust
        self.assertEqual(Test.cmpos, (0, 3, 0))
