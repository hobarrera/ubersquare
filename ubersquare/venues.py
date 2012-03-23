# Copyright (c) 2012 Hugo Osvaldo Barrera <hugo@osvaldobarrera.com.ar>
#
# Permission to use, copy, modify, and distribute this software for any
# purpose with or without fee is hereby granted, provided that the above
# copyright notice and this permission notice appear in all copies.
#
# THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
# WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
# MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR
# ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
# WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN
# ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF
# OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.

#from PySide.QtGui import QDesktopServices
from PySide.QtCore import *
from PySide.QtGui import *
import sys
import foursquare
from foursquare import Cache
from locationProviders import LocationProvider
from custom_widgets import SignalEmittingValueButton, WaitingDialog, CategorySelector, UberSquareWindow
from threads import TipMarkTodoBackgroundThread, TipMarkDoneBackgroundThread, LeaveTipThread
import time

try:
	from PySide.QtMaemo5 import *
	maemo = True
except ImportError:
	maemo = False

from checkins import CheckinConfirmation, CheckinDetails
		
class VenueListModel(QAbstractListModel):
	def __init__(self, venues):
		super(VenueListModel, self).__init__()
		self.venues = venues

	VenueRole = 849561745

	def rowCount(self, role=Qt.DisplayRole):
		if self.venues:
			return len(self.venues)
		else:
			return 0

	def data(self, index, role=Qt.DisplayRole):
		venue = self.venues[index.row()][u'venue']
		if role == Qt.DisplayRole:
			if u'address' in venue[u'location']:
				result = venue[u'name'] + "\n  " + venue[u'location'][u'address']
				if len(result) < 72:
					return result
				else:
					return result[0:67] + "[...]"
			else:
				return venue[u'name']
		elif role == Qt.DecorationRole:
			if len(venue[u'categories']) > 0:
				prefix = venue[u'categories'][0][u'icon'][u'prefix']
				extension = venue[u'categories'][0][u'icon'][u'name']
				return QIcon(foursquare.image(prefix + "64" + extension))
		elif role == VenueListModel.VenueRole:
			return venue

	def setVenues(self, venues):
		self.venues = venues
		self.reset()

class VenueList(QListView):
	def __init__(self, parent, venues):
		super(VenueList,self).__init__(parent)
		self.model = VenueListModel(venues)
		#self.setModel(self.model)
		
		self.proxy = QSortFilterProxyModel(self)
		self.proxy.setSourceModel(self.model)
		self.proxy.setFilterCaseSensitivity(Qt.CaseInsensitive)
		self.setModel(self.proxy)

		self.clicked.connect(self.venue_selected)

	def venue_selected(self, index):
		venue = self.proxy.data(index,VenueListModel.VenueRole)
		cachedVenue = foursquare.venues_venue(venue[u'id'], foursquare.CacheOnly)
		if not cachedVenue:
			d = VenueDetailsWindow(self, venue, False)
		else:
			d = VenueDetailsWindow(self, cachedVenue, True)
		d.show()

	def filter(self,text):
		self.proxy.setFilterRegExp(text)
		self.proxy.filterRegExp()

	def setVenues(self, venues):
		self.model.setVenues(venues)

class VenueListWindow(QMainWindow):
	def __init__(self, title, venues, parent):
		super(VenueListWindow, self).__init__(parent)
		if maemo:
			self.setAttribute(Qt.WA_Maemo5StackedWindow)

		self.setWindowTitle(title)

		self.cw = QWidget(self)
		self.setCentralWidget(self.cw)

		layout = QVBoxLayout(self.cw)

		self.text_field = QLineEdit(self) #QPlainTextEdit es multilinea
		self.text_field.setPlaceholderText("Type to filter")
		self.list = VenueList(self, venues)

		self.text_field.textChanged.connect(self.filter)

		layout.addWidget(self.text_field)
		layout.addWidget(self.list)

		updateVenues = Signal()
		self.connect(self, SIGNAL("updateVenues()"), self._updateVenues)
		self.shown = False

	def show(self):
		super(VenueListWindow, self).show()
		self.shown = True

	def _updateVenues(self):
		self.setVenues(self.parent().venues())
		if not self.shown:
			self.show()

	def filter(self, text):
		self.list.filter(text)

	def setVenues(self, venues):
		self.list.setVenues(venues)

class Tip(QWidget):
	def __init__(self, tip, parent = None):
		super(Tip, self).__init__(parent)

		gridLayout = QGridLayout() 
		self.setLayout(gridLayout) 
		self.tip = tip

		tipLabel = QLabel(tip[u'text'], self)
		tipLabel.setWordWrap(True)
		gridLayout.addWidget(tipLabel, 0, 0, 2, 1)

		self.done_checkbox = QCheckBox("Done! (" + str(tip[u'done'][u'count']) + ")")
		self.done_checkbox.setChecked(self.isTipDone())
		self.done_checkbox.stateChanged.connect(self.markDone)

		self.todo_checkbox = QCheckBox("To-do (" + str(tip[u'todo'][u'count']) + ")")
		self.todo_checkbox.setChecked(self.isTipTodo())
		self.todo_checkbox.stateChanged.connect(self.markTodo)

		gridLayout.addWidget(self.done_checkbox, 0, 1, 1, 1)
		gridLayout.addWidget(self.todo_checkbox, 1, 1, 1, 1)
		gridLayout.setColumnStretch(0, 1)

	def isTipInGroupType(self, groupType):
		if u'listed' in self.tip:
			if u'groups' in self.tip[u'listed']:
				for group in self.tip[u'listed'][u'groups']:
					if group[u'type'] == groupType:
						return True
		return False

	def isTipDone(self):
		return self.isTipInGroupType("dones")
		
	def isTipTodo(self):
		return self.isTipInGroupType("todos")

	def markTodo(self, state):
		TipMarkTodoBackgroundThread(self.tip[u'id'], self.todo_checkbox.isChecked(), self).start()

	def markDone(self, state):
		TipMarkDoneBackgroundThread(self.tip[u'id'], self.done_checkbox.isChecked(), self).start()

class NewTipWidget(QWidget):
	def __init__(self, venueId, parent = None):
		super(NewTipWidget, self).__init__(parent)
		self.__parent = parent

		gridLayout = QGridLayout() 
		self.setLayout(gridLayout) 
		self.venueId = venueId

		self.tip_text = QLineEdit()
		self.tip_text.setPlaceholderText("Write something and then...")
		gridLayout.addWidget(self.tip_text, 0, 0)

		self.tip_button = QPushButton("Leave tip!")
		self.tip_button.clicked.connect(self.addTip)
		gridLayout.addWidget(self.tip_button, 0, 1)

	def addTip(self):
		t = LeaveTipThread(self.venueId, self.tip_text.text(), self.__parent)
		t.start()
		self.__parent.showWaitingDialog.emit()

class Ruler(QFrame):
	def __init__(self):
		super(Ruler, self).__init__()
		self.setFrameShape(QFrame.HLine)
		self.setStyleSheet("QFrame { background-color: #313131; color: #313131; height: 2px; }")

class VenueDetailsWindow(UberSquareWindow):
	def __init__(self, parent, venue, fullDetails):
		super(VenueDetailsWindow, self).__init__(parent)
		self.venue = venue

		self.fullDetails = fullDetails

		self.setWindowTitle(venue[u'name'])

		self.centralWidget = QWidget() 
		self.setCentralWidget(self.centralWidget) 

		layout = QVBoxLayout() 
		layout.setSpacing(0)         
		layout.setContentsMargins(11,11,11,11)
		self.centralWidget.setLayout(layout) 

		self.container = QWidget()

		self.scrollArea = QScrollArea() 
		self.scrollArea.setWidget(self.container)
		self.scrollArea.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

		layout.addWidget(self.scrollArea)   

		self.scrollArea.setWidgetResizable(True)

		gridLayout = QGridLayout() 
		self.container.setLayout(gridLayout) 

		# name
		name = venue[u'name']
		if len(venue[u'categories']) > 0:
			name += " (" + venue[u'categories'][0][u'name'] + ")"

		# address
		address = ""
		if u'address' in venue[u'location']:
			address = venue[u'location'][u'address']

		if u'crossStreet' in venue[u'location']:
			if address != "":
				address += ", "
			address += venue[u'location'][u'crossStreet']

		# address2
		address2 = ""
		if u'postalCode' in venue[u'location']:
			address2 = venue[u'location'][u'postalCode']

		if u'city' in venue[u'location']:
			if address2 != "":
				address2 += ", "
			address2 += venue[u'location'][u'city']

		# times
		if u'beenHere' in venue:
			if not fullDetails:
				count = venue[u'beenHere']
			else:
				count = venue[u'beenHere']['count']
			times = "<b>You've been here "
			if count == 1:
				times += "once"
			else:
				times += str(count) +" times"
			times += "</b>"
		else:
			times = "<b>You've never been here</b>"

		checkin_button = QPushButton("Check-in")
		self.connect(checkin_button, SIGNAL("clicked()"), self.checkin)

		i = 0
		gridLayout.addWidget(checkin_button, i, 1)
		self.shout_text = QLineEdit(self)
		self.shout_text.setPlaceholderText("Shout something")
		gridLayout.addWidget(self.shout_text, i, 0)
		i += 1
		nameLabel = QLabel(name, self)
		nameLabel.setStyleSheet("QLabel { color: #999999; font-size: 36px; }")
		gridLayout.addWidget(nameLabel, i, 0, 1 ,2)
		i += 1
		gridLayout.addWidget(QLabel(address, self), i, 0, 1 ,2)
		i += 1
		gridLayout.addWidget(QLabel(address2, self), i, 0, 1 ,2)
		for item in venue[u'categories']:
			if u'primary' in item and item[u'primary'] == "true":
				i += 1
				gridLayout.addWidget(QLabel(item[u'name'], self), i, 0, 1, 2)
		i += 1
		gridLayout.addWidget(Ruler(), i, 0, 1, 2)

		if u'description' in venue:
			i += 1
			gridLayout.addWidget(QLabel(venue[u'description'], self), i, 0, 1, 2)
			i += 1
			line = QFrame()
			line.setFrameShape(QFrame.HLine)
			gridLayout.addWidget(line, i, 0, 1, 2)

		i += 1
		gridLayout.addWidget(QLabel(times, self), i, 0)
		i += 1
		gridLayout.addWidget(QLabel("Total Checkins: " + str(venue[u'stats'][u'checkinsCount']), self), i, 0)
		i += 1
		gridLayout.addWidget(QLabel("Total Visitors: " + str(venue[u'stats'][u'usersCount']), self), i, 0)

		if u'hereNow' in venue:
			hereNow = venue[u'hereNow'][u'count']
			if hereNow == 0:
				hereNow = "There's no one here now."
			elif hereNow == 1:
				hereNow = "There's just one person here now."
			else:
				hereNow = "There are " + repr(hereNow) + " people here now."
			i += 1
			gridLayout.addWidget(QLabel(hereNow, self), i, 0)

		i += 1
		if u'phone' in venue[u'contact']:
			phoneCallButton = QPushButton("Call")
			phoneCallButton.setIcon(QIcon.fromTheme("general_call"))
			self.connect(phoneCallButton, SIGNAL("clicked()"), self.startPhoneCall)
			gridLayout.addWidget(phoneCallButton, i, 0)
				
		if u'url' in venue:
			websiteButton = QPushButton("Visit Website")
			websiteButton.setIcon(QIcon.fromTheme("general_web"))
			self.connect(websiteButton, SIGNAL("clicked()"), self.openUrl)
			gridLayout.addWidget(websiteButton, i, 1)

		if u'mayor' in venue:
			if u'user' in venue[u'mayor']:
				mayorName = venue[u'mayor'][u'user'][u'firstName']
				mayorCount = venue[u'mayor'][u'count']
				mayorText = mayorName + " is the mayor with " + str(mayorCount) + " checkins!"
				mayorButton = QPushButton()
				mayorButton.setText(mayorText)
				mayorButton.setIcon(QIcon(foursquare.image(venue[u'mayor'][u'user'][u'photo'])))
			else:
				mayorButton = QLabel("This venue has no mayor")
			i += 1
			gridLayout.addWidget(mayorButton, i, 0, 1, 2, Qt.AlignHCenter)

		# TODO: menu
		# TODO: specials

		if u'tips' in venue:
			i += 1
			if venue[u'tips'][u'count'] == 0:
				gridLayout.addWidget(QLabel("<b>There isn't a single tip!</b>", self), i, 0)
			else:
				if venue[u'tips'][u'count'] == 1:
					gridLayout.addWidget(QLabel("<b>Just one tip</b>", self), i, 0)
				else:
					gridLayout.addWidget(QLabel("<b>" + str(venue[u'tips'][u'count']) + " tips</b>", self), i, 0)
				for group in venue[u'tips'][u'groups']:
					for tip in group[u'items']:
						i += 1
						gridLayout.addWidget(Tip(tip), i, 0, 1, 2)
						i += 1
						line = QFrame()
						line.setFrameShape(QFrame.HLine)
						line.setMaximumWidth(QApplication.desktop().screenGeometry().width() * 0.5)
						gridLayout.addWidget(line, i, 0, 1, 2)

			i += 1
			gridLayout.addWidget(NewTipWidget(venue[u'id'], self), i, 0, 1 ,2)

		if not fullDetails:
			info_button_label = "Fetch tips and details"
		else:
			info_button_label = "Force update info"
		more_info_button = QPushButton(info_button_label)
		self.connect(more_info_button, SIGNAL("clicked()"), self.more_info)

		i += 1
		gridLayout.addWidget(more_info_button, i, 0, 1, 2)

		showMoreInfo = Signal()
		self.connect(self, SIGNAL("showMoreInfo()"), self.more_info)

	def startPhoneCall(self):
		QDesktopServices.openUrl("tel:" + self.venue[u'contact']['phone'])

	def openUrl(self):
		QDesktopServices.openUrl(self.venue[u'url'])

	def __showWaitingDialog(self):
		self.waitDialog.exec_()

	def __hideWaitingDialog(self):
		self.waitDialog.hide()

	def more_info(self):
		if not self.fullDetails:
			venue = foursquare.venues_venue(self.venue['id'], Cache.CacheOrNull)
			if venue:
				self.close()
				v = VenueDetailsWindow(self.parent(), venue, True).show()
				return

		# FIXME!
		self.fullDetails = False
		VenueDetailsThread(self.venue['id'], self).start()
		self.__showWaitingDialog()

	def checkin(self):
		c = CheckinConfirmation(self, self.venue)
		c.exec_()
		if c.buttonRole(c.clickedButton()) == QMessageBox.YesRole:
			try:
				ll = LocationProvider().get_ll(self.venue)
				response = foursquare.checkin(self.venue, ll, self.shout_text.text())
				CheckinDetails(self, response).show()
			except IOError:
	 			self.ibox = QMaemo5InformationBox()
	 			self.ibox.information(self, "Network error; check-in failed. Please try again.", 15000)

class VenueDetailsThread(QThread):	
	def __init__(self, venueId, parent):
		super(VenueDetailsThread, self).__init__(parent)
		self.__parent = parent
		self.venueId = venueId
		
	def run(self):
		try:
			venue = foursquare.venues_venue(self.venueId, Cache.ForceFetch)
			if u'mayor' in venue:
				if u'user' in venue[u'mayor']:
					print "there's a mayor!"
					foursquare.image(venue[u'mayor'][u'user'][u'photo'])
			self.__parent.hideWaitingDialog.emit()
			# This tiny sleep in necesary to (a) Avoid an Xorg warning, (b) achieve a smoother transition
			time.sleep(0.15)
			self.__parent.showMoreInfo.emit()
		except IOError:
			self.__parent.hideWaitingDialog.emit()
			self.__parent.networkError.emit()
		self.exec_()
		self.exit(0)

class NewVenueWindow(QMainWindow):
	def __init__(self, parent, categories, ll):
		super(NewVenueWindow, self).__init__(parent)
		self.setAttribute(Qt.WA_Maemo5StackedWindow)
		self.venue = dict()
		self.venue['ignoreDuplicates'] = "false"

		self.setWindowTitle("New Venue")

		self.centralWidget = QWidget() 
		self.setCentralWidget(self.centralWidget) 

		#Main Layout 
		layout = QVBoxLayout() 
		layout.setSpacing(0)         
		self.centralWidget.setLayout(layout) 

		#Content Layout 
		self.container = QWidget() 

		self.scrollArea = QScrollArea() 
		self.scrollArea.setWidget(self.container)           

		layout.addWidget(self.scrollArea)   

		self.scrollArea.setWidgetResizable(True)

		gridLayout = QGridLayout() 
		self.container.setLayout(gridLayout) 

		i = 0
		self.name = QLineEdit(self)
		self.name.setPlaceholderText("Name")
		gridLayout.addWidget(self.name, i, 0, 1, 2)

		i += 1
		self.address = QLineEdit(self)
		self.address.setPlaceholderText("Address")
		gridLayout.addWidget(self.address, i, 0)
		self.crossAddress = QLineEdit(self)
		self.crossAddress.setPlaceholderText("Cross Address")
		gridLayout.addWidget(self.crossAddress, i, 1)

		i += 1
		self.city = QLineEdit(self)
		self.city.setPlaceholderText("City")
		gridLayout.addWidget(self.city, i, 0)
		self.state = QLineEdit(self)
		self.state.setPlaceholderText("State")
		gridLayout.addWidget(self.state, i, 1)
		
		i += 1
		self.zip = QLineEdit(self)
		self.zip.setPlaceholderText("Zip")
		gridLayout.addWidget(self.zip, i, 0)
		self.phone = QLineEdit(self)
		self.phone.setPlaceholderText("Phone")
		gridLayout.addWidget(self.phone, i, 1)
		
		i += 1
		self.twitter = QLineEdit(self)
		self.twitter.setPlaceholderText("Twitter")
		gridLayout.addWidget(self.twitter, i, 0)
		self.url = QLineEdit(self)
		self.url.setPlaceholderText("URL")
		gridLayout.addWidget(self.url, i, 1)

		i += 1
		self.description = QLineEdit(self)
		self.description.setPlaceholderText("Description")
		gridLayout.addWidget(self.description, i, 0, 1, 2)

		i += 1
		self.category = CategorySelector(self)
		gridLayout.addWidget(self.category, i, 0, 2, 2)
		i += 1
		
		i += 1
		self.ll = QLineEdit(self)
		self.ll.setPlaceholderText("Coordinates")
		self.ll.setText(ll)
		gridLayout.addWidget(QLabel("Latitude/Longitude: "), i, 0)
		gridLayout.addWidget(self.ll, i, 1)

		i += 1
		self.add_venue_button = QPushButton("Add Venue")
		self.connect(self.add_venue_button, SIGNAL("clicked()"), self.add_venue)
		gridLayout.addWidget(self.add_venue_button, i, 0, 1 ,2)
		
	def category_selected(self, index):
		if index != -1:
			subcategories = self.category.pickSelector().model().get_data(index)[u'categories']
			self.subcategory.setPickSelector(CategorySelector(subcategories))

	def add_venue(self):
		if self.name.text() == "":
			self.ibox = QMaemo5InformationBox()
			self.ibox.information(self, "No name has been specified for this venue.", 2000)
		if self.ll.text() == "":
			self.ibox = QMaemo5InformationBox()
			self.ibox.information(self, "No ll has been specified for this venue.", 2000)

		venue = dict()
		venue['name'] = self.name.text()
		venue['ll'] = self.ll.text()
		venue['address'] = self.address.text()
		venue['crossAddress'] = self.crossAddress.text()
		venue['city'] = self.city.text()
		venue['state'] = self.state.text()
		venue['zip'] = self.zip.text()
		venue['phone'] = self.phone.text()
		venue['twitter'] = self.twitter.text()
		venue['primaryCategoryId'] = self.category.selectedCategory()
		venue['description'] = self.description.text()
		venue['url'] = self.url.text()
		venue['ignoreDuplicates'] = self.venue['ignoreDuplicates']
		self.venue['ignoreDuplicates'] = "false"
		if 'ignoreDuplicatesKey' in self.venue:
			venue['ignoreDuplicatesKey'] = self.venue['ignoreDuplicatesKey']


		response = foursquare.venue_add(venue)

		if response[u'meta'][u'code'] == 409:
			title = "Duplicate detected"
	
			venues = dict()
			i = 0
			for venue in response[u'response'][u'candidateDuplicateVenues']:
				venues[i] = dict()
				venues[i][u'venue'] = venue
				i +=  1

			msgBox = QMessageBox(self)
			msgBox.setText("Foursquare says this venue looks like a duplicate.<br> Make sure it isn't; if it is, then click \"Add Venue\" again.")
			msgBox.setWindowTitle(title)
			msgBox.exec_()

			self.venue['ignoreDuplicates'] = "true"
			self.venue['ignoreDuplicatesKey'] = response[u'response'][u'ignoreDuplicatesKey']

			w = VenueListWindow("Posible matches", venues, self)
			w.show()
		else:
			msgBox = QMessageBox(self)
			msgBox.setText("Venue successfully created")
			msgBox.setWindowTitle("Venue added")
			msgBox.exec_()

			v = VenueDetailsWindow(self, response[u'response'][u'venue'], True)
			v.show()