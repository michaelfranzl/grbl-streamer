#!/usr/bin/env python
# coding: UTF-8
 
# code extracted from nigiri
 
import os
import datetime
import sys
import traceback
import re
import logging
import locale
import subprocess
 
import urwid
from urwid import MetaSignals

from gerbil import Gerbil
 
 
class ExtendedListBox(urwid.ListBox):
    """
        Listbow widget with embeded autoscroll
    """
 
    __metaclass__ = urwid.MetaSignals
    signals = ["set_auto_scroll"]
 
 
    def set_auto_scroll(self, switch):
        if type(switch) != bool:
            return
        self._auto_scroll = switch
        urwid.emit_signal(self, "set_auto_scroll", switch)
 
 
    auto_scroll = property(lambda s: s._auto_scroll, set_auto_scroll)
 
 
    def __init__(self, body):
        urwid.ListBox.__init__(self, body)
        self.auto_scroll = True
 
 
    def switch_body(self, body):
        if self.body:
            urwid.disconnect_signal(body, "modified", self._invalidate)
 
        self.body = body
        self._invalidate()
 
        urwid.connect_signal(body, "modified", self._invalidate)
 
 
    def keypress(self, size, key):
        urwid.ListBox.keypress(self, size, key)
 
        if key in ("page up", "page down"):
            logging.debug("focus = %d, len = %d" % (self.get_focus()[1], len(self.body)))
            if self.get_focus()[1] == len(self.body)-1:
                self.auto_scroll = True
            else:
                self.auto_scroll = False
            logging.debug("auto_scroll = %s" % (self.auto_scroll))
 
 
    def scroll_to_bottom(self):
        logging.debug("current_focus = %s, len(self.body) = %d" % (self.get_focus()[1], len(self.body)))
 
        if self.auto_scroll:
            # at bottom -> scroll down
            self.set_focus(len(self.body)-1)
 
 
 
"""
 -------context-------
| --inner context---- |
|| HEADER            ||
||                   ||
|| BODY              ||
||                   ||
|| DIVIDER           ||
| ------------------- |
| FOOTER              |
 ---------------------

inner context = context.body
context.body.body = BODY
context.body.header = HEADER
context.body.footer = DIVIDER
context.footer = FOOTER

HEADER = Notice line (urwid.Text)
BODY = Extended ListBox
DIVIDER = Divider with information (urwid.Text)
FOOTER = Input line (Ext. Edit)
"""
 
 
class MainWindow(object):
 
    __metaclass__ = MetaSignals
    signals = ["quit","keypress"]
    # (name, foreground, background, mono, foreground_high, background_high)
    # http://gadgetopia.com/wp-content/uploads/images/build/urwid/reference.html#AttrSpec
    _palette = [
            ('divider', 'black', 'dark cyan'),
            ('fmt_on_log', 'yellow, bold', 'default'),
            ('mybrowntext', 'brown', 'default'),
            ('red', 'dark red', 'default'),
            ('green', 'dark green', 'default'),
            ('bold_text', 'light gray', 'default'),
        ]
 

 
 
    def __init__(self, grbl):
        self.shall_quit = False
        self.grbl = grbl
        self.grbl.set_callback(self.on_callback)
        
    def on_callback(self, event, *data):
        txt = event + " "
        if len(data) > 0:
            txt += ', '.join(str(x) for x in data)
            
        fmt = "fmt_" + event
        
        #text = urwid.Text((fmt, txt))
        if "\033" in txt:
            txt = self.ansi_colors_to_markup(txt)
            
        text = urwid.Text(txt)
        self.print_text(text)
        self.draw_interface()
        
        
    def ansi_colors_to_markup(self, source):
        table = {
            "[31" : 'red',
            "[32" : 'green',
            "[0"  : 'default'
        }
        markup = []
        for at in source.split("\033")[1:]:
            attr, text = at.split("m",1)
            markup.append((table[attr], text))
            
        return markup
 
 
    def main(self):
        """ 
            Entry point to start UI 
        """
 
        self.ui = urwid.raw_display.Screen()
        self.ui.register_palette(self._palette)
        self.build_interface()
        self.ui.run_wrapper(self.run)
 
 
    def run(self):
        """ 
            Setup input handler, invalidate handler to
            automatically redraw the interface if needed.

            Start mainloop.
        """
 
        # I don't know what the callbacks are for yet,
        # it's a code taken from the nigiri project
        def input_cb(key):
            if self.shall_quit:
                raise urwid.ExitMainLoop
            self.keypress(self.size, key)
 
        self.size = self.ui.get_cols_rows()
 
        self.main_loop = urwid.MainLoop(
                self.context,
                screen=self.ui,
                handle_mouse=False,
                unhandled_input=input_cb,
            )
 
        def call_redraw(*x):
            self.draw_interface()
            invalidate.locked = False
            return True
 
        inv = urwid.canvas.CanvasCache.invalidate
 
        def invalidate (cls, *a, **k):
            inv(*a, **k)
 
            if not invalidate.locked:
                invalidate.locked = True
                self.main_loop.set_alarm_in(0, call_redraw)
 
        invalidate.locked = False
        urwid.canvas.CanvasCache.invalidate = classmethod(invalidate)
 
        try:
            self.main_loop.run()
        except KeyboardInterrupt:
            self.quit()
 
 
    def quit(self, exit=True):
        """ 
            Stops the ui, exits the application (if exit=True)
        """
        urwid.emit_signal(self, "quit")
 
        self.shall_quit = True
 
        if exit:
            sys.exit(0)
 
 
    def build_interface(self):
        """ 
            Call the widget methods to build the UI 
        """
 
        self.header = urwid.Text("Chat")
        self.footer = urwid.Edit("> ")
        self.divider = urwid.Text("Initializing.")
 
        self.generic_output_walker = urwid.SimpleListWalker([])
        self.body = ExtendedListBox(self.generic_output_walker)
 
 
        self.header = urwid.AttrWrap(self.header, "divider")
        self.footer = urwid.AttrWrap(self.footer, "footer")
        self.divider = urwid.AttrWrap(self.divider, "divider")
        self.body = urwid.AttrWrap(self.body, "body")
 
        self.footer.set_wrap_mode("space")
 
        main_frame = urwid.Frame(self.body, 
                                header=self.header,
                                footer=self.divider)
        
        self.context = urwid.Frame(main_frame, footer=self.footer)
 
        self.divider.set_text(("divider",
                               ("Send message:")))
 
        self.context.set_focus("footer")
 
 
    def draw_interface(self):
        self.main_loop.draw_screen()
 
 
    def keypress(self, size, key):
        """ 
            Handle user inputs
        """
 
        urwid.emit_signal(self, "keypress", size, key)
 
        # scroll the top panel
        if key in ("page up","page down"):
            self.body.keypress (size, key)
 
        # resize the main windows
        elif key == "window resize":
            self.size = self.ui.get_cols_rows()
 
        elif key in ("ctrl d", 'ctrl c'):
            self.quit()
 
        elif key == "enter":
            # Parse data or (if parse failed)
            # send it to the current world
            text = self.footer.get_edit_text()
 
            self.footer.set_edit_text(" "*len(text))
            self.footer.set_edit_text("")
            exec("self.grbl." + text)
 
            if text in ('quit', 'q'):
                self.quit()
 
            if text.strip():
                self.print_text(text)
 
        else:
            self.context.keypress(size, key)
 
 
 
        
    def print_text(self, text):
        """
            Print the given text in the _current_ window
            and scroll to the bottom. 
            You can pass a Text object or a string
        """
 
        walker = self.generic_output_walker
 
        if not isinstance(text, urwid.Text):
            text = urwid.Text(('test1', text))
 
        walker.append(text)
 
        self.body.scroll_to_bottom()
 
 
    def get_time(self):
        """
            Return formated current datetime
        """
        return datetime.datetime.now().strftime('%H:%M:%S')
        
 
def except_hook(extype, exobj, extb, manual=False):
    if not manual:
        try:
            main_window.quit(exit=False)
        except NameError:
            pass
 
    message = _("An error occured:\n%(divider)s\n%(traceback)s\n"\
        "%(exception)s\n%(divider)s" % {
            "divider": 20*"-",
            "traceback": "".join(traceback.format_tb(extb)),
            "exception": extype.__name__+": "+str(exobj)
        })
 
    logging.error(message)
 
    print >> sys.stderr, message
 
 

 
 
if __name__ == "__main__":
    grbl = Gerbil()
    
    main_window = MainWindow(grbl)
 
    sys.excepthook = except_hook
 
    main_window.main()