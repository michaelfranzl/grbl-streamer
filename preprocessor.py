import re
import logging
module_logger = logging.getLogger('cnctoolbox.preprocessor')
class Preprocessor:
    def __init__(self):
        self.logger = logging.getLogger('cnctoolbox.preprocessor')
        self.line = "; preprocessor_init"
        self._feed_override = False
        self._requested_feed = None
        self._current_feed = None
        
        self._vars = {}
        
        self.callback = self._default_callback
        
        self._re_var = re.compile(".*#(\d)")
        self._re_var_assign = re.compile(".*#(\d)=([\d.-]+)")
        self._re_var_replace = re.compile(r"#\d")
        self._re_feed = re.compile(".*F([.\d]+)")
        self._re_feed_replace = re.compile(r"F[.\d]+")
        self.logger.info("Preprocessor Class Initialized")
        
        
    def cleanup(self):
        """
        Called after Grbls has booted. Mimics Grbl's state machine. After boot, Grbl's feed is not set.
        """
        self._current_feed = 0
        self.callback("on_feed_change", self._current_feed)
    
    
    def set_feed_override(self, val):
        self._feed_override = val
        self.logger.info("FEED OVERRIDING: {}".format(val))
        #logging.log(260, "Preprocessor: Feed override set to %s", val)
            
        
    def request_feed(self, val):
        self._requested_feed = val
        #logging.log(260, "Preprocessor: Feed request set to %s", val)
        
        
    def tidy(self, line):
        #self.logger.info("Preprocessor.tidy Beginning {}".format(line))
        self.line = line
        self._strip_comments()
        self._strip_unsupported()
        self._handle_vars()
        #self.logger.info("Preprocessor.tidy Returning {}".format(self.line))
        self._strip()
        return self.line
        
        
    def handle_feed(self, line):
        self.line = line
        self._handle_feed()
        return self.line
    
    
    def _strip_unsupported(self):
        """
        This silently strips gcode unsupported by Grbl, but ONLY those commands that are safe to strip without making the program deviate from its original purpose. For example it is  safe to strip a tool change. All other encountered unsupported commands should be sent to Grbl nevertheless so that an error is raised. The user then can make an informed decision.
        """
        if "T" in self.line or "M6" in self.line:
            self.line = "".format(self.line)
        
        
        
    def _strip_comments(self):
        """
        strip comments (after semicolon and opening parenthesis)
        """
        self.line = re.match("([^;(]*)", self.line).group(1)
        self.line += ""


    def _strip(self):
        """
        Remove blank spaces and newlines from beginning and end,
        and remove blank spaces from the middle of the line.
        """
        self.line = self.line.strip()
        self.line = self.line.replace(" ", "")
        
        
    def _handle_vars(self):
        match = re.match(self._re_var_assign, self.line)
        contains_var_assignment = True if match else False
        if contains_var_assignment:
            key = int(match.group(1))
            val = float(match.group(2))
            self._vars[key] = val
            self.callback("on_log", "SET VAR #{}={}".format(key, val))
            #self.line = "; cnctools_var_set {}".format(self.line)
            self.line = ""
            return
        
        match = re.match(self._re_var, self.line)
        contains_var = True if match else False
        if contains_var:
            key = int(match.group(1))
            if key in self._vars:
                val = str(self._vars[key])
                self.line = re.sub(self._re_var_replace, val, self.line)
                self.callback("on_log", "SUBSTITUED VAR #{} -> {}".format(key, val))
            else:
                self.callback("on_log", "VAR #{} UNDEFINED".format(key))
   
   
    def _handle_feed(self):
        match = re.match(self._re_feed, self.line)
        contains_feed = True if match else False
        
        
        if self._feed_override == False and contains_feed:
            # Simiply update the UI for detected feed
            parsed_feed = float(match.group(1))
            if self._current_feed != parsed_feed:
                self.callback("on_feed_change", parsed_feed)
            self._current_feed = float(parsed_feed)
            
            
        if self._feed_override == True and self._requested_feed:
            if contains_feed:
                # strip the original F setting
                self.line = re.sub(self._re_feed_replace, "", self.line)
                
            if self._current_feed != self._requested_feed:
                self.line += "F{:0.1f}".format(self._requested_feed)
                self._current_feed = self._requested_feed
                self.callback("on_log", "OVERRIDING FEED: " + str(self._current_feed))
                self.callback("on_feed_change", self._current_feed)
                    
            
            
    def _default_callback(self, status, *args):
        print("PREPROCESSOR DEFAULT CALLBACK", status, args)
