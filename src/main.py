import kivy
kivy.require('2.1.0')

from kivy.app import App
from kivy.uix.label import Label
from kivy.uix.tabbedpanel import TabbedPanel
from kivy.lang import Builder

class OSMGUI(TabbedPanel):
    pass

Builder.load_file('gui.kv')

class PyOSMXP(App):
    def build(self):
        return OSMGUI()
    

if __name__ == '__main__':
    PyOSMXP().run()