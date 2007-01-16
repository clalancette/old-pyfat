from array import *

def ascii(x):
	if 32 <= x <= 126:
		return chr(x)
	elif 160 <= x <= 255:
		return '.'
	else:
		return '.'

def hexdump(string, width=16, start=0):
	pos = 0
	ascmap = [ascii(x) for x in xrange(256)]
	lastbuf = ''
	lastline = ''
	nStarLen = 0

	if start:
		pos = start

	while(1):
		buf = string[pos:pos+width]
		pos += 1
		length = len(buf)

		if length == 0:
			if nStarLen:
				if nStarLen > 1:
					print "* %d" % (nStarLen-1)
				elif nStarLen == 1:
					print lastline
				print lastline
			return

		if buf == lastbuf:
			nStarLen += 1


		hex = ""
		asc = ""
		for i in xrange(length):
			c = buf[i]
			if i == width/2:
				hex += " "
			hex = hex + ("%02x" % ord(c)) + " "
			asc = asc + ascmap[ord(c)]
		line = "%6x: %-49s %s" % (pos, hex, asc)
		print line

		pos += length
		lastbuf = buf
		lastline = line

def toInt(string):
	ret = 0
	for i in xrange(len(string)):
		ret += (int(string[i]) << (i*8))

	return ret

def toIntReverse(string):
	ret = 0
	for i in xrange(len(string)):
		ret += (int(string[-(i+1)]) << (i*8))

	return ret

def make_string(bytes):
	ba = array('B')
	ba.fromlist(bytes)
	return ba.tostring()

def fromInt(num):
	"""Returns an array from an integer"""
	ret = []
	for i in xrange(4): #Change for arbitrary range
		# x % 0xFF
		# x >> 4
