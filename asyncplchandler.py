from twisted.internet import serialport, reactor
from twisted.internet.protocol import ClientFactory
from pymodbus.factory import ClientDecoder
from pymodbus.client.async import ModbusClientProtocol
from serial import PARITY_NONE, PARITY_EVEN, PARITY_ODD
from serial import STOPBITS_ONE, STOPBITS_TWO
from serial import FIVEBITS, SIXBITS, SEVENBITS, EIGHTBITS
from pymodbus.transaction import ModbusAsciiFramer as ModbusFramer

from abstracthandler import AbstractHandler
from pydispatch import dispatcher


class SMHSProtocol(ModbusClientProtocol):

    def __init__(self, framer, endpoint, pol_list, logger):
        ''' Initializes our custom protocol

        :param framer: The decoder to use to process messages
        :param endpoint: The endpoint to send results to
        '''
        ModbusClientProtocol.__init__(self, framer)
        self.endpoint = endpoint
        self.pol_list = pol_list
        self.logger = logger
        self.logger.debug("Beggining the processing loop")
        reactor.callLater(3, self.fetch_holding_registers)

    def fetch_holding_registers(self):
        for t in self.pol_list:
            if t in ["inputc"]:
                address_map = self.pol_list[t]
                for registers in address_map:
                    d = self.read_holding_registers(*registers)
                    d.addCallbacks(self.start_next_cycle, self.error_handler)

    def start_next_cycle(self, response):
        self.logger.error(response.getRegister(0))
        reactor.callLater(3, self.fetch_holding_registers)

    def error_handler(self, failure):
        self.logger.error(failure)


class SMHSFactory(ClientFactory):

    protocol = SMHSProtocol

    def __init__(self, framer, endpoint, pol_list, logger):
        self.framer = framer
        self.endpoint = endpoint
        self.pol_list = pol_list
        self.logger = logger

    def buildProtocol(self, _):
        proto = self.protocol(
            self.framer, self.endpoint, self.pol_list, self.logger)
        proto.factory = self
        return proto


class SerialModbusClient(serialport.SerialPort):

    def __init__(self, factory, *args, **kwargs):
        protocol = factory.buildProtocol(None)
        self.decoder = ClientDecoder()
        serialport.SerialPort.__init__(self, protocol, *args, **kwargs)


class LoggingLineReader(object):

    def __init__(self, logger):
        self.logger = logger

    def write(self, response):
        self.logger.info("Read Data: %d" % response)


class asyncplchandler(AbstractHandler):

    def __init__(self, parent=None, params={}):
        AbstractHandler.__init__(self, parent, params)
        self.logger.info("Init async_plchandler")
        serverconfig = params["server"]
        self.serial_port = params["port"]
        self.pollint = serverconfig["pollingTimeout"]
        self.packetSize = int(serverconfig["packetSize"])
        self.tagslist = {}
        #fill tagslist with tags from all types
        for tagtype in self.config:
            self.tagslist.update(self.config[tagtype])

    def _generate_address_map(self, addressList):
        '''
        generate addressMap based on the addressList
        addressMap is dictionary with key = startaddress to read
        and value = number of bits need to read
        '''
        keylist = addressList.keys()
        maxAddress = int(max(keylist))
        minAddress = int(min(keylist))
        s = maxAddress - minAddress + 1
        c, d = divmod(s, self.packetSize)
        l = maxAddress - d + 1
        addressMap = []
        for x in range(0, c):
            curAddress = minAddress + self.packetSize * x
            addressMap.append((curAddress, self.packetSize,))
        if (d > 0):
            addressMap.append((l, d,))
        return tuple(addressMap)

    def run(self):
        AbstractHandler.run(self)
        framer = ModbusFramer(ClientDecoder())
        reader = LoggingLineReader(self.logger)
        fullAddressList = {}
        for x in self.tagslist:
            if "address" in self.tagslist[x]:
                address = self.tagslist[x]["address"]
                fullAddressList[address] = x
        pol_list = {}
        for t in self.config.keys():
            if t in ["output", "input", "inputc"]:
                address_list = {}
                for x in self.config[t]:
                    address = self.tagslist[x]["address"]
                    address_list[address] = x
                pol_list[t] = self._generate_address_map(address_list)
        factory = SMHSFactory(framer, reader, pol_list, self.logger)
        SerialModbusClient(
            factory, "/dev/plc",
            reactor, baudrate=9600,
            parity=PARITY_EVEN, bytesize=SEVENBITS,
            stopbits=STOPBITS_TWO, timeout=3)

    def stop(self):
        AbstractHandler.stop(self)
