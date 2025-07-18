#!/usr/bin/python
from __future__ import absolute_import, division, print_function, unicode_literals
import RPi.GPIO as gpio
import time
import sys
import os
import socket
import threading
from subprocess import call, check_output, CalledProcessError

exitApp = False
wifi_connected = False
ip_ready = False
disconnect = False


def main():
    print('Running LED Script')
    L1 = 28
    L2 = 40
    L3 = 41
    freqPWM = 1000
    dcOn = 10  # set max brightness at 10, any more than that and eyes hurt
    dcOff = 0

    gpio.setmode(gpio.BCM)
    gpio.setup(L1, gpio.OUT)
    gpio.setup(L2, gpio.OUT)
    gpio.setup(L3, gpio.OUT)
    pwm1 = gpio.PWM(L1, freqPWM)
    pwm2 = gpio.PWM(L2, freqPWM)
    pwm3 = gpio.PWM(L3, freqPWM)

    def setIpGlobal(newValue):
        global ip_ready
        global disconnect
        if not newValue and ip_ready:
            disconnect = True
        if newValue and not ip_ready:
            disconnect = False
        ip_ready = newValue

    def getIPAddress():
        # purpose: check if hostname has resolved yet
        try:
            output = check_output(['hostname', '-I'])
            return output
        except CalledProcessError as e:
            print('Error getting ip address: %s' % e)
            return None

    def getInterfaceStatus():
        # purpose: check interface connection status
        try:
            output = check_output(['sudo', 'iw', 'dev', 'wlan0', 'link'])
            return output
        except CalledProcessError as e:
            print('Error getting iw link status: %s' % e)
            return None

    def flashAll3Led():
        while True:
            turnL1On()
            turnL2On()
            turnL3On()
            time.sleep(1)
            turnL1Off()
            turnL2Off()
            turnL3Off()
            time.sleep(1)

    def turnL1On():
        pwm1.start(100 - dcOn)

    def turnL2On():
        pwm2.start(dcOn)

    def turnL3On():
        pwm3.start(dcOn)

    def turnL1Off():
        pwm1.start(100 - dcOff)

    def turnL2Off():
        pwm2.start(dcOff)

    def turnL3Off():
        pwm3.start(dcOff)

    def checkWiFiConnection():
        global wifi_connected
        while not exitApp:
            # check wlan0 status
            status = getInterfaceStatus()
            if status:
                if 'Not connected.' in status:
                    wifi_connected = False
                else:
                    wifi_connected = True
            # check hotspot IP address status
            hotspot_status = getIPAddress()
            if '.' in hotspot_status:
                setIpGlobal(True)
            else:
                setIpGlobal(False)
            time.sleep(2)
        return

    def checkPaletteConnection():
        while not exitApp:
            paletteFlagPath = '/home/pi/.mosaicdata/palette_flag'
            if os.path.exists(paletteFlagPath):
                turnL2On()
            else:
                turnL2Off()
            time.sleep(2)
        return

    def checkPrinterConnection():
        while not exitApp:
            printerFlagPath = '/home/pi/.mosaicdata/printer_flag'
            if os.path.exists(printerFlagPath):
                turnL3On()
            else:
                turnL3Off()
            time.sleep(2)
        return

    def checkL1Output():
        global wifi_connected
        global ip_ready
        minDC = 0
        maxDC = 20
        dc1 = minDC
        dc2 = maxDC
        up = True
        t = time.time()
        period = 0.0001
        while not exitApp:
            if ip_ready:
                if gpio.gpio_function(L1) != gpio.OUT:
                    gpio.setup(L1, gpio.OUT)
                if not wifi_connected:
                    t = time.time()
                    gpio.output(L1, gpio.LOW)
                    time.sleep(dc1 * period)

                    t = time.time()
                    gpio.output(L1, gpio.HIGH)
                    time.sleep((100 - dc1) * period)

                    if up:
                        dc1 = dc1 + 0.2
                    else:
                        dc1 = dc1 - 0.2
                    if(dc1 >= maxDC):
                        up = False
                        dc1 = maxDC
                    elif(dc1 <= minDC):
                        up = True
                        dc1 = minDC
                else:
                    t = time.time()
                    gpio.output(L1, gpio.LOW)
                    time.sleep(dc2 * period)

                    t = time.time()
                    gpio.output(L1, gpio.HIGH)
                    time.sleep((100 - dc2) * period)
            else:
                gpio.output(L1, gpio.LOW)
                time.sleep(0.3)
                gpio.output(L1, gpio.HIGH)
                time.sleep(0.3)
        return

    def runHotspot():
        global disconnect
        while not exitApp:
            if disconnect:
                call(['sudo /usr/bin/autohotspot'], shell=True)
            time.sleep(30)
        return

    # 0. Check for WiFi chip
    try:
        usb_output = check_output(['lsusb'])
        if 'Ralink Technology, Corp. RT5370 Wireless Adapter' not in usb_output:
            print('WiFi chip not found.')
            flashAll3Led()
    except CalledProcessError as e:
        print('Error getting lsusb status: %s' % e)
        print('Could not obtain USB buses information.')
        flashAll3Led()

    # 1. Remove existing flags at start up, if any
    paletteFlagPath = '/home/pi/.mosaicdata/palette_flag'
    printerFlagPath = '/home/pi/.mosaicdata/printer_flag'
    if os.path.exists(paletteFlagPath):
        call(['rm %s' % paletteFlagPath], shell=True)
    if os.path.exists(printerFlagPath):
        call(['rm %s' % printerFlagPath], shell=True)

    # 2. Initialize thread to check for WiFi connection
    wifiThread = threading.Thread(target=checkWiFiConnection, name='WiFi Thread')
    wifiThread.start()

    # 3. Wait for IP hostname to resolve before continuing
    global ip_ready
    while not ip_ready:
        pwm1.start(0)
        time.sleep(0.3)
        pwm1.start(100)
        time.sleep(0.3)
    pwm1.stop()

    # 4. Initalize thread to check for palette connection
    paletteThread = threading.Thread(target=checkPaletteConnection, name='Palette Thread')

    # 5. Initalize thread to check for printer connection
    printerThread = threading.Thread(target=checkPrinterConnection, name='Printer Thread')

    # 6. Initialize thread for L1 light
    L1Thread = threading.Thread(target=checkL1Output, name='L1 Thread')

    # 7. Initialize thread for hotspot script
    hotspotThread = threading.Thread(target=runHotspot, name='Hotspot Thread')

    # 8. Start threads
    paletteThread.start()
    printerThread.start()
    L1Thread.start()
    hotspotThread.start()

    while not exitApp:
        time.sleep(1)

    # 9. End threads
    wifiThread.join()
    paletteThread.join()
    printerThread.join()
    L1Thread.join()
    hotspotThread.join()
    gpio.cleanup()


if __name__ == '__main__':
    try:
        main()
    except:
        print('Stopping LED script')
        exitApp = True
        sys.exit()
