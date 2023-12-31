import unittest
import time
import logging

from grbl_streamer import GrblStreamer

formatter = logging.Formatter()

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
        if event == 'on_stateupdate':
            cls.cmode = args[0]
            cls.cmpos = args[1]

        data = formatter.format(args[0]) if event == 'on_log' else args
        print('{}: {}'.format(event.rjust(30, ' '), data))


    @classmethod
    def setUpClass(cls):
        cls.grbl = GrblStreamer(cls.callback)
        cls.grbl.setup_logging()
        # cls.grbl.setup_logging(logging.StreamHandler())
        cls.grbl.cnect('/dev/ttyUSB0', 115200)
        time.sleep(3)  # TODO: Make this more robust
        cls.grbl.poll_start()

    @classmethod
    def tearDownClass(cls):
        cls.grbl.disconnect()

    def test(self):
        Test.grbl.write('G59')  # use any coordinate system that is in the machine origin
        Test.grbl.write('G0 Y3')
        Test.grbl.job_run()
        time.sleep(3)  # TODO: Make this more robust
        self.assertEqual(Test.cmpos, (0, 3, 0))
