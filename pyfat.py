import os
import os.path

import util

from array import *
import logging
logging.basicConfig(level=logging.DEBUG)

SECTOR_SIZE = 512
ERASED_ENTRY = 0xE5
EMPTY_ENTRY = 0x00
SUBDIR_ENTRY = 0x2E

READ_ONLY = 0x01
HIDDEN = 0x02
SYSTEM = 0x04
VOL_LABEL = 0x08
SUBDIR = 0x10
ARCHIVE = 0x20

DIR_DELIM = "\\"


class Disk:
	def __init__(self, filename):
		self.image = DiskImage(filename)
		self.boot = PartitionBootSector(self.image[0])
		self.fat1 = Fat12(self.image[1:10])
		self.fat2 = Fat12(self.image[10:19])
		self.root_dir = Directory(self.image[19:33],root=True)
		self.data = self.image[33:]

	def __getitem__(self, key):
		"""Returns the byte array for the given filename."""

		full_path = key.split(DIR_DELIM)
		dirs = full_path[:-1]
		working_dir = self.open_dir(dirs)

		return self.load_file(working_dir,full_path[-1])
		

	def open_dir(self, dir_list):
		"""
		Loads the directory table from the directory file.
		
		This function receives the directory hierarchy as a list where the
		first element is a root directory entry and the last element is the
		directory that will be open. Example:
		
		\\one\\two\\three => ['one', 'two', 'three']
		
		If the list is empty, returns the root directory for this partition.
		"""
		
		current_dir = self.root_dir

		for current in dir_list:
			logging.debug("Current dir: %s" % current)
			contents = self.load_dir(current_dir, current)
			current_dir = Directory(contents)

		return current_dir

	def load_dir(self, dir, dir_name):
		"""
		Loads the data for a directory file.
		
		Keyword arguments:
		dir - Parent directory
		dir_name - Name of the directory
		"""
	
		#TODO Merge with load file? (Ignore that file_size stuff)
		entry = None

		try:
			entry = dir[dir_name]
		except KeyError:
			raise "FileNotFound"

		cluster = entry.starting_cluster
		data = []

		cluster_size = self.boot.sectors_per_cluster*self.boot.bytes_per_sector

		while(cluster != 0xFFF):
			cluster_data = self.data[cluster-2]
			data.extend(cluster_data)
			cluster = self.fat1[cluster]
			logging.debug("Next cluster = %x", cluster)

		return data

	def load_file(self, dir, filename):
		"""
		Loads the data for a directory file.
		
		Keyword arguments:
		dir - Parent directory
		filename - Name of the file
		"""
		entry = None
		try:
			logging.debug("Trying to get file %s" % filename)
			entry = dir[filename]
		except KeyError:
			raise "FileNotFound"

		cluster = entry.starting_cluster
		file_size = entry.file_size
		data_read = 0
		data = []
		
		cluster_size = self.boot.sectors_per_cluster*self.boot.bytes_per_sector

		while(cluster != 0xFFF and data_read < file_size):
			cluster_data = self.data[cluster-2] # exclude reserved clusters
			remaining_data = file_size - data_read
			if cluster_size <= remaining_data:
				data.extend(cluster_data)
				data_read += cluster_size
			else:
				data.extend(cluster_data[:remaining_data])

			cluster = self.fat1[cluster]

		return data
	

	def cluster(self, key):
		"""Returns a cluster from the data area."""
		return self.data[key]


class PartitionBootSector:
	def __init__(self, sector):
		self.id = sector[0x03:0x0B]
		self.bytes_per_sector = util.toInt(sector[0x0B:0x0D])
		self.sectors_per_cluster = util.toInt(sector[0x0D:0x0E])
		self.reserved_sectors = util.toInt(sector[0x0E:0x10])
		self.fats = util.toInt(sector[0x10:0x11])
		self.root_entries = util.toInt(sector[0x11:0x13])
		self.small_sectors = util.toInt(sector[0x13:0x15])
		self.media_type = util.toInt(sector[0x15:0x16])
		self.sectors_per_fat = util.toInt(sector[0x16:0x18])
		self.sectors_per_track = util.toInt(sector[0x18:0x1A])
		self.head_number = util.toInt(sector[0x1A:0x1C])
		self.hidden_sectors = util.toInt(sector[0x1C:0x20])
		self.large_sectors = util.toInt(sector[0x20:0x24])
		self.drive_number = util.toInt(sector[0x24:0x25])
		self.flags = util.toInt(sector[0x25:0x26])
		self.signature = sector[0x26:0x27]
		self.volume_id = sector[0x27:0x2B]
		self.volume_label = sector[0x2B:0x36]
		self.system_id = sector[0x36:0x3E]

	def __repr__(self):
		return "Partition id %s - Volume %s - System %s"  % (
			util.make_string(self.id), util.make_string(self.volume_label),
			util.make_string(self.system_id))

class Directory:
	"""
	This class stores the directory table for a given directory.
	"""
	def __init__(self, data, root=False):
		self.entries = {}

		# When creating the root directory we recieve a list of sectors, so
		# we need to 
		if root:
			tmp = data[0][:]
			for i in xrange(len(data)-1):
				tmp.extend(data[i+1])
			data = tmp

		for i in xrange(len(data)/32):
			entry = DirectoryEntry(data[32*i:32*(i+1)])
			logging.debug("Entry %d = %s" % (i, entry.name))
			
			if (entry.attribute != 0x0F) and not (entry.erased() or entry.empty()) :
				if not entry.subdir():
					key = entry.name + '.' + entry.extension
				else:
					key = entry.name
	
				logging.debug("Adding key %s" % key)
				self.entries[key] = entry

		self.count = 0

	def __getitem__(self, key):
		"""Returns the directory entry with 'key' filename."""
		return self.entries[key]

	def __iter__(self):
		return self
	
	def next(self):
		if self.count == len(self.entries):
			self.count = 0
			raise StopIteration
		self.count += 1
		return self[self.entries.keys()[self.count -1]]

	# Not needed as we aren't dealing with erased files (not added to the table)
	#def cleanup_erased(self):
	#	for k in self.entries.keys():
	#		if(self[k].erased()):
	
	
class DirectoryEntry:
	def __init__(self, entry):
		self.name = util.make_string(entry[0x00:0x08]).strip().lower() # 8 bytes
		self.extension = util.make_string(entry[0x08:0x0B]).strip().lower() # 3 bytes
		self.attribute = entry[0x0B:0x0C][0] # 1 byte
		self.reserved = entry[0x0C:0x0D][0] # 1 byte
		self.create_time = entry[0x0D:0x10] # 3 bytes
		self.create_date = entry[0x10:0x12] # 2 bytes
		self.last_access_date = entry[0x12:0x14] # 2 bytes
		self.long_starting_cluster = entry[0x14:0x16]
		self.last_modified_time = entry[0x16:0x18] # 2 bytes
		self.last_modified_date = entry[0x18:0x1A] # 2 bytes
		self.starting_cluster = util.toInt(entry[0x1A:0x1C]) # 2 bytes
		self.file_size = util.toInt(entry[0x1C:0x20]) # 4 bytes

	def __repr__(self):
		return "Name: %s.%s - Size %d" % (self.name, self.extension,
			self.file_size)

	def subdir(self):
		return self.attribute & SUBDIR != 0

	def erased(self):
		return ord(self.name[0]) == ERASED_ENTRY

	def empty(self):
		return ord(self.name[0]) == EMPTY_ENTRY


class Fat12:
	"""
	This class stores the FAT12.
	"""
	def __init__(self, sectors):
		'''Receives a list of sectors'''

		# Merging the sectors
		self.list = sectors[0][:]
		for i in xrange(len(sectors)-1):
			self.list.extend(sectors[i+1])
		
		self.count = 0

	def __len__(self):
		return len(self.list)*8/12

	def __getitem__(self, key):
		"""Gets the entry at offset given by key"""
		absolute_bits = 12*key
		first_byte = absolute_bits / 8
		value = 0x00

		if absolute_bits % 8 == 0:
			value = int(self.list[first_byte])
			value += (int(self.list[first_byte+1]) & 0x0F) << 8
		else:
			value = int(self.list[first_byte+1]) << 4
			value += (int(self.list[first_byte]) & 0xF0) >> 4 

		return value
	
	def __iter__(self):
		return self

	def next(self):
		if self.count == len(self):
			self.count = 0
			raise StopIteration

		self.count += 1
		return self[self.count-1]

	def next_empty_entry(self):
		for k,v in enumerate(self):
			if v == 0x000:
				return k
		return -1


class DiskImage:
	"""Abstraction of a disk image. Loads the entire image on memory"""
	def __init__(self, filename, sector_size=SECTOR_SIZE):
		self.filename = filename
		self.sector_size = sector_size
		self.buffer, self.size = self.loadFile(filename)
		self._counter = 0

	def loadFile(self, filename):
		'''Loads a file into an array of 512-byte sectors'''
		file = open(filename, "rb")
		buffer = []
			
		size = os.stat(filename).st_size
	
		for i in xrange(size/self.sector_size + 1):
			buffer.append(map(ord,list(file.read(self.sector_size))))
	
		file.close()
		return (buffer,i)
	
	def dumpFile(self, filename=None, overwrite=False):
		'''Dumps an array of 512-bytes sectors into a file '''

		if not filename:
			filename = self.filename

		if os.path.exists(filename) and not overwrite:
			return # Returns quietly

		file = open(filename, "wb")
		file.writelines(self.buffer)
		file.close()

	def appendData(self, data):
		data_size = len(data)
		last_sector_size = len(self.buffer[len(self._buffer)-1])
		new_space = data_size - last_sector_size
		new_sectors = new_space * SECTOR_SIZE + 1

		last_sector = self._buffer[self._size -1]

	def __repr__(self):
		return "File: %s - Size: %d sectors" % (self.filename, self.size)

	def __len__(self):
		return len(self.buffer)

	def __getitem__(self, key):
		return self.buffer[key]

	def __setitem__(self, key, value):
		self.buffer[key] = value

	def __iter__(self):
		return self

	def next(self):
		if self._counter == self.size:
			self._counter = 0
			raise StopIteration

		self._counter += 1
		return self.buffer[self._counter - 1]

	def mbr(self):
		return self[0]


if __name__ == "__main__":
	a = Disk("floppy.img")
	print a.boot

	print util.make_string(a['foo.txt'])
	print util.make_string(a['zee\\foo.txt'])
