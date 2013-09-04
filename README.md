#Soundcloud TCP server challange


Current version: 0.1.1

###Usage
All code is tested using Python 2.7.3. It will *not* run in Python 3.
To run the server:

	python server.py

To run automatic tests:

	python unit_testing.py

The server will run using background threads, hence TCP_server.stop should be polled to detect when the server has successfully shut down. 
The general usage in an external script is:

	from server import TCP_server
	
	try:
		s = TCP_server(HOST, EVENT_SOURCE_PORT, USER_CLIENT_PORT, BUFFER_SIZE, timeout=TIMEOUT, test_mode=True)
		s.start_server()
	except ValueError:
		s.stop_server()
		sys.exit(1)
	
	while not s.stop.is_set():
		try:
			time.sleep(1)
		except (KeyboardInterrupt):
			s.stop_server()

###Testing log
A google doc documenting the versions and testing is provided [here](https://docs.google.com/spreadsheet/ccc?key=0AiLh1_T0qNxcdDU0QnJJbnZxUjdCR093XzBvdndGZ1E&usp=sharing).

###Known issues
* Connections to sockets during the automatic testing are temperamental. Must include long waits to allow the sockets to reset themselves. This cannot be avoided.