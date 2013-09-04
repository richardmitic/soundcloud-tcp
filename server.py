#!/opt/local/bin/python

import socket, threading, time, sys, heapq


HOST = '127.0.0.1'
EVENT_SOURCE_PORT = 9090
USER_CLIENT_PORT = 9099
BUFFER_SIZE = 4096  # Max TCP message size
TIMEOUT = 20.
MAXQUEUE = 1000

VERBOSE = True


"""
TODO:	DONE Move thread activation to separate function
		DONE Add global timeout when there is no activity
		DONE Find proper way to stop threads
		DONE Make connections with IP4 and IP6
		DONE Set max queue length
		DONE Add test mode that will close server when any connection is terminated remotely
		DONE Think about raising a ValueError is timeout is out of range
		DONE Timeouts on waiting for users to connect
"""


def printout(text):
	if VERBOSE:
		print text


class Client():
	"""
	Store client connections to the TCP server.
	Connections are non-blocking.
    
	:param ID: ID number recieved from client on connection.
	:param conn: Connection used to send messages.
	:param addr: Client network address.
	"""
	def __init__(self, ID, conn, addr):
		self.ID = ID
		self.conn = conn
		if self.conn:
			self.conn.setblocking(0) # So that we can catch exceptions if user disconnects
		self.addr = addr
		self.followers = []
	
	def get_info(self):
		print "Client:: ID:{0} conn:{1} addr:{2} followers{3}".format(self.ID, self.conn, self.addr, self.followers)
		
	def close_socket(self):
		"""
		Close connection to this client
		"""
		try:
			# self.conn.shutdown(socket.SHUT_RD)
			self.conn.close()
			self.conn = None
		except: pass

	def send(self, payload):
		"""
		Send message to this client. If sending fails, assume connection is dead and nullify it.
		"""
		try:
			self.conn.send(payload)
			printout("Message {0} sent to {1}".format(payload.replace("\n", r"\n"), self.ID))
		except (socket.error, AttributeError):
			self.conn = None
			self.addr = None
			printout("Message {0} to {1} dropped".format(payload.replace("\n", r"\n"), self.ID))

	def add_follower(self, to_user_id):
		"""
		Add follower to list if not already there.
		"""
		if not to_user_id in self.followers:
			self.followers.append(to_user_id)
    
	def remove_follower(self, to_user_id):
		"""
		Remove follower from list if there.
		"""
		try:
			self.followers.pop(self.followers.index(to_user_id))
		except:
			pass


class TCP_server():
	"""
	TCP server to process incoming events and generate notifcations for connected clients.
	
	Keyword arguments:
	timeout -- If timeout is not None, the server will shut down after a period of no activity that lasts for the given time in seconds. (default None)
	test_mode -- If test_mode is True, the server will shut down when any connection is terminated remotely. Designed for use with FollowerMaze-assembly-1.0.jar. (default False) 
	maxqueue -- Maximum number of messages allowed in the queue.
	"""
	def __init__(self, host, event_source_port, user_client_port, tcp_buffer_size=4096, timeout=None, test_mode=False, maxqueue=1000):
		# Sanity checks
		if maxqueue < 1 or tcp_buffer_size < 1 or (timeout and timeout <= 0):
			raise ValueError
		
		self.clients = []
		self.event_buffer = ''
		self.shutdown = False

		self.host = host
		self.event_source_port = event_source_port
		self.user_client_port = user_client_port
		self.tcp_buffer_size = tcp_buffer_size
		self.timeout = timeout
		self.test_mode = test_mode
		self.maxqueue = maxqueue

		if timeout: self.timeout_lock = threading.Lock()
		self.client_list_lock = threading.Lock()
		self.event_buffer_lock = threading.Lock()
		self.stop = threading.Event()
		
		if timeout: self.TO = Server_timeout(self)
		self.UC = User_client_handler(self)
		self.EL = Event_listener(self)
		self.EP = Event_parser(self)
		
		# Make threads deamonic so they will end when main thread ends
		if timeout: self.TO.daemon = True
		self.UC.daemon = True
		self.EL.daemon = True
		self.EP.daemon = True

	def get_connection(self, host, port):
		"""
		Get connection using IPv4 or IPv6 (whichever is available first).
		See http://docs.python.org/2/library/socket.html#example
		"""
		s = None
		err = None
		num_connection_attempts = 3
		time_between_connection_attempts = self.timeout/(num_connection_attempts+1) if self.timeout else 5.
		for attempts in xrange(1,1+num_connection_attempts):
			for res in socket.getaddrinfo(host, port, socket.AF_UNSPEC, socket.SOCK_STREAM, 0, socket.AI_PASSIVE):
				family, socktype, proto, canonname, sockaddress = res
				try:
					s = socket.socket(family, socktype, proto)
				except socket.error:
					s = None
					continue
				try:
					s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
					s.bind(sockaddress)
					s.listen(1)
				except socket.error as e:
					err = e
					s.close()
					s = None
					continue
				break
			if s is None:
				print "ERROR: could not open socket {0} after {1} attempts".format(sockaddress, attempts)
				print str(err)
				time.sleep(time_between_connection_attempts)
				continue
			else:
				break
		return s

	def start_server(self):
		"""Start all server threads. Connections are opened inside threads."""
		print "\n::: TCP server starting :::\n"
		if self.timeout: self.TO.start()
		self.EL.start()
		self.UC.start()
		self.EP.start()		
	
	def stop_server(self):
		"""
		Tell all threads to close and break connections. Function is prevented from being called by more than one thread.
		"""
		if not self.shutdown:
			self.shutdown = True
			
			# Close connections to clients
			for c in self.clients:
				c.close_socket()
				
			# Stop threads. Connections are closed inside thread
			try: self.UC.stop.set()
			except: pass
			try: self.EL.stop.set()
			except: pass
			try: self.EP.stop.set()
			except: pass
			try: self.TO.stop.set()
			except: pass
		
			print "\n::: TCP server stopped :::\n"
			self.stop.set()

	def add_client(self, c):
		"""
		Add client to list or edit a currently existing one.
		"""
		try:
			current = filter(lambda client: client.ID == c.ID, self.clients)[0]
			current.conn = c.conn
			current.addr = c.addr
			return current
		except IndexError:
			self.clients.append(c)
			return self.clients[-1]

	def reset_timer(self):
		if self.timeout:
			self.TO.reset()


class Server_timeout(threading.Thread):
	"""
	Timer that will stop the server if there is no activity for the specified time.
	
	:param server: The instance of TCP_server that owns the thread.
	"""
	def __init__(self, server):
		threading.Thread.__init__(self)
		self.server = server
		self.last_reset = 0.
		self.reset()
		self.stop = threading.Event()
	
	def run(self):
		while not self.stop.is_set():
			t = self.get_last_reset()
			if time.time() > t+self.server.timeout:
				print "::: No activity for {0}s. Closing server. :::".format(self.server.timeout)
				self.server.stop_server()
			time.sleep(1) # Check for timeout once per second
		printout("Timeout thread terminated")
	
	def reset(self):
		with self.server.timeout_lock:
			self.last_reset = time.time()
	
	def get_last_reset(self):
		with self.server.timeout_lock:
			return self.last_reset


class User_client_handler(threading.Thread):
	"""
	Thread to handle connections to clients.
	
	:param server: The instance of TCP_server that owns the thread.
	"""
	def __init__(self, server):
		threading.Thread.__init__(self)
		self.server = server
		self.stop = threading.Event()
	
	def cleanup(self):
		try:
			self.soc.close()
			self.soc = None
		except: pass

	def run(self):
		# Main loop to allow connection if not in test_mode
		while not self.stop.is_set():
			# Connect to port
			self.soc = self.server.get_connection(self.server.host, self.server.user_client_port)
		
			# If socket is invalid, shut down the server.
			if not self.soc:
				self.server.stop_server()
				return
		
			# Wait for clients to connect
			self.soc.settimeout(1.)
			self.server.reset_timer()
			print "Wating for incoming connections..."
			while not self.stop.is_set():
				try:
					conn, addr = self.soc.accept()
					conn.settimeout(1.)
					self.server.reset_timer()
				
					# Get ID from client and store
					data = conn.recv(self.server.tcp_buffer_size)
					self.server.reset_timer()
					if data:
						try:
							client_id = int(data)
							with self.server.client_list_lock:
								self.server.add_client(Client(client_id, conn, addr))
							print "Client {0} connected on address: {1}".format(client_id, addr)
						except ValueError:
							print "Client {0} attempted to connect, but gave bad ID".format(data)
					else:
						break # detect broken connection
				except socket.timeout:
					pass
			
			# Error with socket detected...
			self.cleanup() 
			if self.server.test_mode:
				self.server.stop_server()
		
		self.stop.set()
		printout("User client thread terminated")


class Event_listener(threading.Thread):
	"""
	Thread to accept and buffer incoming events.
	
	:param server: The instance of TCP_server that owns the thread.
	"""
	def __init__(self, server):
		threading.Thread.__init__(self)
		self.server = server
		self.stop = threading.Event()
	
	def cleanup(self):
		try:
			self.conn.close()
			self.conn = None
		except: pass
		try:
			self.soc.close()
			self.soc = None
		except: pass

	def run(self):
		# Main loop to allow connection if not in test_mode
		while not self.stop.is_set():
			# Connect to port
			self.soc = self.server.get_connection(self.server.host, self.server.event_source_port)
			
			# If socket is invalid, shut down the server.
			if not self.soc:
				self.server.stop_server()
				return

			# Wait for event source to connect 
			self.soc.settimeout(1.)
			self.server.reset_timer()
			while not self.stop.is_set():
				try:
					self.conn, self.addr = self.soc.accept()
					self.conn.settimeout(1.)
					self.server.reset_timer()
					break
				except socket.timeout:
					pass

			if not self.stop.is_set():
				print 'Event source connected on address:', self.addr
		
			# Start receiving data from event source.
			while not self.stop.is_set():
				try:
					data = self.conn.recv(self.server.tcp_buffer_size)
					self.server.reset_timer()
					if data:
						with self.server.event_buffer_lock:
							self.server.event_buffer += data
					else:
						break # detect broken connection
				except socket.timeout:
					pass
			
			# Error with socket detected...
			self.cleanup() 
			if self.server.test_mode:
				self.server.stop_server()
				break
		
		self.stop.set()
		printout("Event listener thread terminated")


class Event_parser(threading.Thread):
	"""
	Thread to parse event buffer and handle parsed events.
	
	:param server: The instance of TCP_server that owns the thread.
	"""
	def __init__(self, server):
		threading.Thread.__init__(self)
		self.server = server
		self.queue = []
		self.next_msg = 1
		self.stop = threading.Event()

	def run(self):
		while not self.stop.is_set():
			# Get messages from buffer
			msgs = self.extract_messages()
			if msgs:
				self.server.reset_timer()
				# If queue is overflowing, drop messages that haven't arrived and flush.
				if len(self.queue)+len(msgs) > self.server.maxqueue:
					self.next_msg = self.queue[0][0]
					self.flush()
				# Add new messages to queue if they have not already been dropped by queue overflow protection.
				for msg in msgs:
					seq = int(msg.split('|', 1)[0]) 
					if seq >= self.next_msg:
						heapq.heappush(self.queue, (seq,msg))
				self.flush()
			time.sleep(0.01)
		printout("Event parser thread terminated")

	def flush(self):
		"""
		Process due events and clear them from the queue
		"""
		while self.queue: # Make sure queue is not empty
			if self.queue[0][0] == self.next_msg:
				seq, msg = heapq.heappop(self.queue)
				self.process_event(msg)
				self.next_msg += 1
				self.server.reset_timer()
			else:
				break

	def extract_messages(self):
		"""
		Split buffer into complete messages and residual.
		:return: List of complete messages. List can be empty.
		"""
		with self.server.event_buffer_lock:
			# If no complete messages, return empty list and do not touch buffer
			last_newline_idx = self.server.event_buffer.rfind("\n")
			if last_newline_idx > -1:
				if self.server.event_buffer:
					# Split and return available messages
					complete_msgs = self.server.event_buffer[:last_newline_idx+1]

					# Remove processed data from buffer but leave residual
					if len(complete_msgs) != len(self.server.event_buffer):
						self.server.event_buffer = self.server.event_buffer[last_newline_idx+1:] 
					else:
						self.server.event_buffer = ''
					return complete_msgs.splitlines(True)
			return []

	def process_event(self, msg):
		"""
		Process a single event from the queue.
		"""
		try:
			# Get data common to all events
			parts = msg.strip("\n").split('|')
			seq = int(parts[0])
			event_type = parts[1]

			# Process message depending on type
			if event_type == 'F':
				self.msg_f(msg, parts)
			elif event_type == 'U':
				self.msg_u(msg, parts)	
			elif event_type == 'B':
				self.msg_b(msg, parts)
			elif event_type == 'P':
				self.msg_p(msg, parts)
			elif event_type == 'S':
				self.msg_s(msg, parts)
		except (IndexError, ValueError):
			print "WARNING: badly formatted message {0} dropped".format(msg.replace("\n", r"\n"))

	def msg_f(self, msg, parts):
		"""
		Follow message:: Update followers of to_user. Notify to_user. If to_user doesn't exist in client list, create it and add follower.
		"""
		from_user_id = int(parts[2])
		to_user_id = int(parts[3])
		with self.server.client_list_lock:
			try:
				to_user = filter(lambda client: client.ID == to_user_id, self.server.clients)[0]
				to_user.add_follower(from_user_id)
				to_user.send(msg)
				printout("Message {0} sent to client".format(msg.replace("\n", r"\n"), to_user_id))
			except IndexError:
				new = self.server.add_client(Client(to_user_id, None, None))
				new.add_follower(from_user_id)
				printout("Message {0} dropped".format(msg.replace("\n", r"\n")))
	
	def msg_u(self, msg, parts):
		"""
		Unfollow message:: Update followers of to_user. Do not notify.
		"""
		from_user_id = int(parts[2])
		to_user_id = int(parts[3])
		with self.server.client_list_lock:
			try:
				to_user = filter(lambda client: client.ID == to_user_id, self.server.clients)[0]
				to_user.remove_follower(from_user_id)
			except IndexError:
				# If to_user is not in list of connections, it hasn't been created, and therefore cannot have any followers.
				# If we were keeping track of who a user is following, we would deal with that here.
				pass

	def msg_b(self, msg, parts):
		"""
		Broadcast:: Notify all connected users
		"""
		with self.server.client_list_lock:
			for client in self.server.clients:
				if client.conn:
					client.send(msg)
		printout("Message {0} broadcast to all".format(msg.replace("\n", r"\n")))

	def msg_p(self, msg, parts):
		"""
		Private message:: Notify to_user.
		"""
		from_user_id = int(parts[2])
		to_user_id = int(parts[3])
		try:
			with self.server.client_list_lock:
				to_user = filter(lambda client: client.ID == to_user_id, self.server.clients)[0]
				to_user.send(msg)
		except IndexError:
			printout("Private message {0} dropped".format(msg.replace("\n", r"\n")))
			pass

	def msg_s(self, msg, parts):
		"""
		Status update:: Notify all followers of from_user.
		"""
		from_user_id = int(parts[2])
		try:
			with self.server.client_list_lock:
				from_user = filter(lambda client: client.ID == from_user_id, self.server.clients)[0]
				for f in from_user.followers:
					try:
						to_user = filter(lambda client: client.ID == to_user_id, self.server.clients)[0]
						if to_user.con:
							to_user.send(msg)
							printout("Status update {0} sent to {1}".format(msg.replace("\n", r"\n"), to_user_id))
					except IndexError:
						pass # Drop message if follower is not connected
		except:
			printout("Status update {0} dropped".format(msg.replace("\n", r"\n")))
			pass # Drop notification if from_user is not connected



if __name__ == "__main__":
	try:
		s = TCP_server(HOST, EVENT_SOURCE_PORT, USER_CLIENT_PORT, BUFFER_SIZE, timeout=TIMEOUT, test_mode=False)
		s.start_server()
	except ValueError:
		s.stop_server()
		sys.exit(1)
	
	while not s.stop.is_set():
		try:
			time.sleep(1)
		except (KeyboardInterrupt):
			s.stop_server()
			
			













    