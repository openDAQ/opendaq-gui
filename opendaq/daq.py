#!/usr/bin/env python

# Copyright 2012
# Adrian Alvarez <alvarez@ingen10.com> and Juan Menendez <juanmb@ingen10.com>
#
# This file is part of opendaq.
#
# opendaq is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# opendaq is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with opendaq.  If not, see <http://www.gnu.org/licenses/>.

import struct
import time
import serial

BAUDS = 115200
INPUT_MODES = ('ANALOG_INPUT', 'ANALOG_OUTPUT', 'DIGITAL_INPUT',
               'DIGITAL_OUTPUT', 'COUNTER_INPUT', 'CAPTURE_INPUT')
LED_OFF = 0
LED_GREEN = 1
LED_RED = 2

class LengthError(Exception):
    pass

class CRCError(Exception):
    pass


def crc(data):
    s = 0
    for c in data: s += ord(c)
    return struct.pack('>H', s)

def check_crc(data):
    csum = data[:2]
    payload = data[2:]
    if csum != crc(payload):
        raise CRCError
    return payload

def check_stream_crc(head, data):
    csum = (head[0]<<8) + head[1]
    return csum == sum(head[2:] + data)


class DAQ:
    def __init__(self, port):
        self.port = port
        self.open()

    def open(self):
        self.ser = serial.Serial(self.port, BAUDS, timeout=.1)
        self.ser.setRTS(0)
        time.sleep(2)

    def close(self):
        self.ser.close()

    def send_command(self, cmd, ret_fmt, debug=False):
        # add 'command' and 'length' fields to the format string
        fmt = '>bb' + ret_fmt
        ret_len = 2 + struct.calcsize(fmt)
        packet = crc(cmd) + cmd

        self.ser.write(packet)
        ret = self.ser.read(ret_len)

        if debug:
            print 'Command:  ',
            for c in packet:
                print '%02X' % ord(c),
            print
            print 'Response: ',
            for c in ret:
                print '%02X' % ord(c),
            print

        if len(ret) != ret_len:
            raise LengthError

        data = struct.unpack(fmt, check_crc(ret))

        if data[1] != ret_len-4:
            raise LengthError

        # strip 'command' and 'length' values from returned data
        return data[2:]

    def get_info(self):
        return self.send_command('\x27\x00', 'bbI')

    def read_adc(self):
        return self.send_command('\x01\x00', 'h')[0]

    def conf_adc(self, pinput, ninput=0, gain=1, nsamples=20):
        cmd = struct.pack('BBBBBB', 2, 4, pinput, ninput, gain, nsamples)
        return self.send_command(cmd, 'hBBBB')
    
    def enable_crc(self, on):
        cmd = struct.pack('BBB', 55, 1, on)
        return self.send_command(cmd, 'B')[0]

    def set_led(self, color):
        if not 0 <= color <= 2:
            raise ValueError('Invalid color number')
        cmd = struct.pack('BBB', 18, 1, color)
        return self.send_command(cmd, 'B')[0]

    def set_dac(self, volts):
        value = int(round(volts*1000))
        if not -4096 < value < 4096:
            raise ValueError('DAQ voltage out of range')
        cmd = struct.pack('>BBh', 13, 2, value)
        return self.send_command(cmd, 'h')[0]
        
    def set_port_dir(self, output):
        cmd = struct.pack('BBB', 9, 1, output)
        return self.send_command(cmd, 'B')[0]

    def set_port(self, value):
        cmd = struct.pack('BBB', 7, 1, value)
        return self.send_command(cmd, 'B')[0]

    def set_pio_dir(self, number, output):
        if not 1 <= number <= 6:
            raise ValueError('Invalid PIO number')
        cmd = struct.pack('BBBB', 5, 2, number,  int(bool(output)))
        return self.send_command(cmd, 'BB')

    def set_pio(self, number, value):
        if not 1 <= number <= 6:
            raise ValueError('Invalid PIO number')
        cmd = struct.pack('BBBB', 3, 2, number, int(bool(value)))
        return self.send_command(cmd, 'BB')

    def init_counter(self, edge):
        cmd = struct.pack('>BBB', 41, 1, 1)
        return self.send_command(cmd, 'B')[0]

    def get_counter(self, reset):
        cmd = struct.pack('>BBB', 42, 1, reset)
        return self.send_command(cmd, 'H')[0]

    def init_capture(self, period):
        cmd = struct.pack('>BBH', 14, 2, period)
        return self.send_command(cmd, 'H')[0]

    def stop_capture(self):
        self.send_command('\x15\x00', '')

    def get_capture(self, mode):
        cmd = struct.pack('>BBB', 16, 1, mode)
        return self.send_command(cmd, 'BH')
    
    def init_encoder(self, resolution):
        cmd = struct.pack('>BBB', 50, 1, resolution)
        return self.send_command(cmd, 'B')[0]

    def stop_encoder(self):
        self.send_command('\x33\x00', '')

    def get_encoder(self):
        return self.send_command('\x34\x00', 'H')
    
    def init_pwm(self, duty, period):
        cmd = struct.pack('>BBHH', 10, 4, duty, period)
        return self.send_command(cmd, 'HH')
     
    def stop_pwm(self):
        self.send_command('\x0b\x00', '')

    def __get_calibration(self, gain_id):
        cmd = struct.pack('>BBB', 36, 1, gain_id)
        return self.send_command(cmd, 'BHh')
        
    def get_cal(self):
        gains = []
        offsets = []

        for i in range(5):
            gain_id, gain, offset = self.__get_calibration(i)
            gains.append(gain)
            offsets.append(offset)

        return gains, offsets
            
    def __set_calibration(self, gain_id, gain, offset):
        cmd = struct.pack('>BBBHh', 37, 5, gain_id, gain, offset)
        return self.send_command(cmd, 'BHh')

    def set_cal(self, gains, offsets):
        for i in range(5):
            self.__set_calibration(i, gains[i], offsets[i])
    
    def conf_channel(self, number, mode, pinput, ninput=0, gain=1, nsamples=1):
        if not 1 <= number <= 4:
            raise ValueError('Invalid number')
        if type(mode) == str and mode in INPUT_MODES:
            mode = INPUT_MODES.index(mode)
        cmd = struct.pack('>BBBBBBBB', 22, 6, number, mode, 
                          pinput, ninput, gain, nsamples)
        return self.send_command(cmd, 'BBBBBB')

    def setup_channel(self, number, npoints, continuous=True):
        if not 1 <= number <= 4:
            raise ValueError('Invalid number')
        cmd = struct.pack('>BBBHb', 32, 4, number, npoints, int(continuous))
        return self.send_command(cmd, 'BHB')

    def destroy_channel(self, number):
        if not 1 <= number <= 4:
            raise ValueError('Invalid number')
        cmd = struct.pack('>BBB', 57, 1, number)
        return self.send_command(cmd, 'B')
        
    def create_stream(self, number, period):
        if not 1 <= number <= 4:
            raise ValueError('Invalid number')
        if not 1 <= period <= 65535:
            raise ValueError('Invalid period')
        cmd = struct.pack('>BBBH', 19, 3, number, period)
        return self.send_command(cmd, 'BH')
        
    def create_burst(self, period):
        cmd = struct.pack('>BBH', 21, 2, period)
        return self.send_command(cmd, 'H')

    def create_external(self, number, edge):
        if not 1 <= number <= 4:
            raise ValueError('Invalid number')
        cmd = struct.pack('>BBBB', 20, 2, number, edge)
        return self.send_command(cmd, 'BB')

    def load_signal(self, data, offset):
        cmd = struct.pack('>bBh%dh' % len(data), 23, len(data), offset, *data)
        return self.send_command(cmd, 'Bh')

    def start(self):
        self.send_command('\x40\x00', '')

    def stop(self):
        self.send_command('\x50\x00', '')
        
    def flush(self):
        self.ser.flushInput()

    def flush_stream(self, data, channel):
        #receive all stream data in the in buffer
        while 1:
            ret = self.ser.read(1)
            if len(ret)==0:
                break
            else:
                cmd = struct.unpack('>b',ret)
                if cmd[0] == 0x7E:
                    self.header = []
                    self.data = []
                    while len(self.header)<8:
                        ret = self.ser.read(1)
                        char = struct.unpack('>B',ret)
                        if char[0] == 0x7D:
                            ret = self.ser.read(1)
                        self.header.append(char[0])
                    length=self.header[3]
                    self.dataLength=length-4
                    while len(self.data)<self.dataLength:
                        ret = self.ser.read(1)
                        char = struct.unpack('>B',ret)
                        if char[0] == 0x7D:
                            ret = self.ser.read(1)
                            char = struct.unpack('>B',ret)
                            tmp = char[0] | 0x20
                            self.data.append(tmp)
                        else:
                            self.data.append(char[0])
                    if check_stream_crc(self.header,self.data)!=1:
                        continue
                    for i in range(0, self.dataLength, 2):
                        value = (self.data[i]<<8) | self.data[i+1]
                        if value >=32768:
                            value=value-65536
                        data.append(int(value))
                        channel.append(self.header[4]-1)
                else:
                    break
        
        ret = self.ser.read(3)
        ret = str(cmd[0])+ret
        if len(ret) !=4:
            raise LengthError

    #This function get stream from serial.
    #Returns 0 if there aren't any incoming data
    #Returns 1 if data stream was precessed
    #Returns 2 if no data stream received. Useful for debuging
    def get_stream(self, data, channel):
        header = []

        ret = self.ser.read(1)
        if len(ret)==0:
            return 0
        head = struct.unpack('>b',ret)
        if head[0] != 0x7E:
            data.append(head[0])
            return 2
        #get header

        while len(header)<8:
            ret = self.ser.read(1)
            char = struct.unpack('>B',ret)
            if char[0] == 0x7D:
                ret = self.ser.read(1)
                char = struct.unpack('>B',ret)
                tmp = char[0] | 0x20
                header.append(tmp)
            else:
                header.append(char[0])
                
            if len(header)==3 and header[2] == 80:
                #ODaq send stop
                ret = self.ser.read(2)
                char,ch = struct.unpack('>BB',ret)
                channel.append(ch-1)
                return 3

        length=header[3]
        dataLength=length-4
        while len(data)<dataLength:
            ret = self.ser.read(1)
            char = struct.unpack('>B',ret)
            if char[0] == 0x7D:
                ret = self.ser.read(1)
                char = struct.unpack('>B',ret)
                tmp = char[0] | 0x20
                data.append(tmp)
            else:
                data.append(char[0])
        
        for i in range(0, dataLength, 2):
            value = (data[i]<<8) | data[i+1]
            if value >=32768:
                value=value-65536
            data.append(int(value))

        check_stream_crc(header,data)
        channel.append(header[4]-1)

        return 1


if __name__ == '__main__':
    import time, sys

    daq = DAQ('/dev/ttyUSB0')

    daq.create_stream(1, 100)
    daq.conf_channel(1, 'ANALOG_INPUT', 1)
    daq.setup_channel(1, 200)
    daq.start()

    data = []
    channel = []
    for i in xrange(20):
        daq.get_stream(data, channel)

    print data
    daq.flush()
    daq.stop()
    #daq.conf_channel(channel, mode, pinput, ninput=0, gain=1, nsamples=1)
    #daq.setup_channel(channel, npoints, continuous=True)
    #daq.destroy_channel(channel):