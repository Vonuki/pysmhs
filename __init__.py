'''
Created on Jan 25, 2012

@author: pavel
'''

if __name__ == '__main__':
    from corehandler import corehandler
    c = corehandler(None, {"configfile": "config/coreconfig.txt"})
    while c.isAlive():
        try:
            c.join(1)
        except KeyboardInterrupt:
            c.stop()
    print "END"
