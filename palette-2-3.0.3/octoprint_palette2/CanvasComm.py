from __future__ import absolute_import, division, print_function, unicode_literals
import octoprint.server
def getLog(msg, module='palette-2-to-canvas-comm', topic=''):
    if topic == '':
        return '{ "msg": "' + msg + '", "module": "' + module +'" }'
    else:
        return '{ "msg": "' + msg + '", "module": "' + module +'", "topic": "' + topic +'" }'
class CanvasComm:
    def __init__(self, plugin):
        self.plugin = plugin
        self.logger = plugin.logger
        self._plugin_manager = plugin._plugin_manager
        self._register_message_receiver()

    def _register_message_receiver(self):
        self.logger.info(getLog('setting palette 2 plugin message reciever'))
        version = octoprint.server.VERSION
        version = version.split('.')
        if int(version[1]) > 3:
            self._plugin_manager.register_message_receiver(self._on_message_v1_4)
        else:
            self._plugin_manager.register_message_receiver(self._on_message)

    def _on_message_v1_4(self, plugin, data, permissions=None):
        if plugin == 'canvas-plugin':
            if data == 'connect':
                self.logger.info(getLog('connect to palette 2', topic='connect'))
                self.plugin.palette.connectOmega(None)
            elif data == 'disconnect':
                self.logger.info(getLog('disconnect from palette 2',  topic='disconnect'))
                self.plugin.palette.disconnect()
        pass

    def _on_message(self, plugin, data):
        if plugin == 'canvas-plugin':
            if data == 'connect':
                self.logger.info(getLog('connect to palette 2',  topic='connect'))
                self.plugin.palette.connectOmega(None)
            elif data == 'disconnect':
                self.logger.info(getLog('disconnect from palette 2',  topic='disconnect'))
                self.plugin.palette.disconnect()
        pass

    def send_message(self, data):
        self.logger.info(getLog(str(data), 'send-to-canvas'))
        self._plugin_manager.send_plugin_message(plugin="palette2", data=data)
        pass