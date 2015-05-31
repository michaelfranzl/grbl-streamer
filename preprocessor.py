""" Python module "Gerbil" (c) 2015 Red (E) Tools Ltd.

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
"""

import re
import logging

class Preprocessor:
    """ This class should receive all G-Code lines before they are sent out to the Grbl controller. It's main features are:
    
    * variable substitution (e.g. #1, #2 etc.)
    * dynamic feed override
    * code cleanup (comments, spaces, unsupported commands)
    
    Callbacks:
    
    on_preprocessor_feed_change
    : Emitted when a F keyword is parsed from the G-Code.
    : 1 argument: the feed rate in mm/min

    on_preprocessor_var_undefined
    : Emitted when a variable is to be substituted but no substitution value has been set previously.
    : 1 argument: the key of the undefined variable
    """
    
    def __init__(self):
        self.logger = logging.getLogger('gerbil.preprocessor')
        self.line = ""
        self.vars = {}
        self.callback = self._default_callback
        self.logger.info("Preprocessor Class Initialized")
        self.feed_override = False
        
        self.request_feed = None
        self._current_feed = None
        self._re_findall_vars = re.compile("#(\d)")
        self._re_var_replace = re.compile(r"#\d")
        self._re_feed = re.compile(".*F([.\d]+)")
        self._re_feed_replace = re.compile(r"F[.\d]+")
        
    def job_new(self):
        """
        Resets state information for a new job.
        """
        self.vars = {}
        
    def onboot_init(self):
        """
        Call this after Grbl has booted. Mimics Grbl's internal state.
        """
        self._current_feed = 0 # After boot, Grbl's feed is not set.
        self.callback("on_preprocessor_feed_change", self._current_feed)
        
    
    def set_vars(self, vars):
        """
        Define variables and their substitution.
        
        @param vars
        A dictionary containing variable names and values. E.g. {"1":3, "2":4}
        """
        self.vars = vars
        
        
    def tidy(self, line):
        """
        Strips G-Code not supported by Grbl, comments, and cleans up spaces in G-Code for slightly reduced serial bandwidth. Returns the tidy line.
        
        @param line
        A single G-Code line
        """
        self.line = line
        self._strip_comments()
        self._strip_unsupported()
        self._strip()
        return self.line
    
    
    def find_vars(self, line):
        """
        Parses all #1, #2, etc. variables in a G-Code line and populates the internal `vars` dict. After this function is done, the dict will not have any values set.
        
        @param line
        A single G-Code line
        """
        keys = re.findall(self._re_findall_vars, self.line)
        for key in keys:
            self.vars[key] = None
        
        
    def substitute_vars(self, line):
        """
        Does actual #1, #2, etc. variable substitution based on the values previously stored in the `vars` dict. When a variable is to be substituted but no substitution value has been set previously in the `vars` dict, a callback "on_preprocessor_var_undefined" will be made and no substitution done. If this happens, it is an User error and the stream should be stopped.
        
        @param line
        A single G-Code line
        """
        self.line = line
        keys = re.findall(self._re_findall_vars, self.line)
        
        for key in keys:
            val = None
            if key in self.vars:
                val = self.vars[key]
            
            if val == None:
                self.line = ""
                self.callback("on_preprocessor_var_undefined", key)
                return self.line
            else:
                self.line = self.line.replace("#" + key, val)
                self.callback("on_log", "SUBSTITUED VAR #{} -> {}".format(key, val))
            
        return self.line
    
        
    def handle_feed(self, line):
        """
        Optionally does dynamic feed override.
        
        @param line
        A single G-Code line
        """
        self.line = line
        self._handle_feed()
        return self.line
    
    
    def _strip_unsupported(self):
        # This silently strips gcode unsupported by Grbl, but ONLY those commands that are safe to strip without making the program deviate from its original purpose. For example it is  safe to strip a tool change. All other encountered unsupported commands should be sent to Grbl nevertheless so that an error is raised. The user then can make an informed decision.
        if ("T" in self.line or # tool change
            "M6" in self.line or # tool change
            re.match("#\d=.*", self.line) # var assignment
            ): 
            self.line = ""
        
        
    def _strip_comments(self):
        # strip comments (after semicolon and opening parenthesis)
        self.line = re.match("([^;(]*)", self.line).group(1)
        self.line += ""


    def _strip(self):
        # Remove blank spaces and newlines from beginning and end, and remove blank spaces from the middle of the line.
        self.line = self.line.strip()
        self.line = self.line.replace(" ", "")

   
    def _handle_feed(self):
        match = re.match(self._re_feed, self.line)
        contains_feed = True if match else False
        
        if self.feed_override == False and contains_feed:
            # Simiply update the UI for detected feed
            parsed_feed = float(match.group(1))
            if self._current_feed != parsed_feed:
                self.callback("on_preprocessor_feed_change", parsed_feed)
            self._current_feed = float(parsed_feed)
            
            
        if self.feed_override == True and self.request_feed:
            if contains_feed:
                # strip the original F setting
                self.line = re.sub(self._re_feed_replace, "", self.line)
                
            if self._current_feed != self.request_feed:
                self.line += "F{:0.1f}".format(self.request_feed)
                self._current_feed = self.request_feed
                self.callback("on_log", "OVERRIDING FEED: " + str(self._current_feed))
                self.callback("on_preprocessor_feed_change", self._current_feed)
                

    def _default_callback(self, status, *args):
        print("PREPROCESSOR DEFAULT CALLBACK", status, args)
