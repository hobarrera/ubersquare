try:
	import location
except ImportError:
	print "Couldn't import location. You're probably not running maemo."
	print "GPS Support disabled."

import foursquare

class LocationProvider:
	"""
	Borg singlton object
	"""
	__we_are_one = {}
	__providers = []
	__selectedProvider = None

	def init(self):
		self.register(AGPSLocationProvider())
		self.register(LastCheckinLocationProvider())
		self.register(AproximateVenueLocationProvider())
		self.register(CellTowerProvider())

	def __init__(self):
		self.__dict__ = self.__we_are_one

	def providers(self):
		return self.__providers

	def register(self, provider):
		self.__providers.append(provider)

	def len(self):
		return len(self.__providers)

	def get(self, index):
		return self.__providers[index]

	def get_ll(self, venue = None):
		if not self.__selectedProvider:
			return None
		return self.__selectedProvider.get_ll(venue)

	def select(self, index):
		if self.__selectedProvider:
			self.__selectedProvider.unselect()
		self.__selectedProvider = self.get(index)
		self.__selectedProvider.select()

class AGPSLocationProvider:
	def __init__(self):
		self.control = location.GPSDControl.get_default()
		self.device = location.GPSDevice()

	def get_ll(self, venue = None):
		lat = "%2.8f" % self.device.fix[4]
		lng = "%2.8f" % self.device.fix[5]
		return lat + "," + lng

	def get_name(self):
		return "Use the builtin AGPS w/network positioning"

	def select(self):
		self.control.set_properties(preferred_method=location.METHOD_ACWP|location.METHOD_AGNSS)
		self.control.start()
		
	def unselect(self):
		self.control.stop()

class LastCheckinLocationProvider:
	def get_ll(self, venue = None):
		ll = foursquare.config_get("last_ll")
		if not ll:
			ll = foursquare.get_last_ll()
		if venue:
			lat = "%2.8f" % venue[u'location'][u'lat']
			lng = "%2.8f" % venue[u'location'][u'lng']
			foursquare.config_set("last_ll", lat + "," + lng)
		return ll

	def get_name(self):
		return "Use the location of the last checkin"

	def select(self):
		pass
		
	def unselect(self):
		pass

class AproximateVenueLocationProvider:
	def get_ll(self, venue = None):
		if not venue:
			return LastCheckinLocationProvider().get_ll()
		venueId = venue[u'id']
		lat = float((ord(venueId[0]) + (ord(venueId[1])*100)))/(10000*10000) + venue[u'location'][u'lat']
		lat = "%2.8f" % lat
		lng = float((ord(venueId[2]) + (ord(venueId[3])*100)))/(10000*10000) + venue[u'location'][u'lng']
		lng = "%2.8f" % lng
		ll = lat + "," + lng
		print ll
		return ll

	def get_name(self):
		return "Use a location close to a venue"

	def select(self):
		pass
		
	def unselect(self):
		pass

class CellTowerProvider:
	def __init__(self):
		self.control = location.GPSDControl.get_default()
		self.device = location.GPSDevice()

	def get_ll(self, venue = None):
		lat = "%2.8f" % self.device.fix[4]
		lng = "%2.8f" % self.device.fix[5]
		return lat + "," + lng

	def get_name(self):
		return "Use cell tower positioning"

	def select(self):
		self.control.set_properties(preferred_method=location.METHOD_ACWP)
		self.control.start()
		
	def unselect(self):
		self.control.stop()