import unittest
from server import TCP_server, Client
from time import time, sleep
import os
import threading

HOST = '127.0.0.1'
EVENT_SOURCE_PORT = 9090
USER_CLIENT_PORT = 9099
BUFFER_SIZE = 4096  # Max TCP message size
TIMEOUT = 20.
MAXQUEUE = 1000
VERBOSE = True


# @unittest.skip('skipped')
class GeneralTesting(unittest.TestCase):
	def setUp(self):
		self.s = TCP_server(HOST,
							EVENT_SOURCE_PORT,
							USER_CLIENT_PORT,
							BUFFER_SIZE,
							timeout=TIMEOUT,
							test_mode=True)
	
	def tearDown(self):
		self.s.stop_server()
		sleep(10) # Allow time for sockets to be released and threads to terminate
		self.s = None
	
	def test_1_followermaze(self):
		# Run follower maze, catch output and get
		SEED=666
		EVENTS=1000
		CONCURRENCY=7
		self.s.start_server()
		command = "time java -server -XX:-UseConcMarkSweepGC -Xmx2G -jar ./follower-maze2/FollowerMaze-assembly-1.0.jar {0} {1} {2} > maze.log".format(SEED,EVENTS,CONCURRENCY)
		ret = os.system(command)
		while not self.s.stop.is_set():
			pass
		self.assertEqual(ret, 0)
	
	def test_2_timeout(self):
		# Check timeout is accurate to +/- 1s
		start = time()
		self.s.start_server()
		while not self.s.stop.is_set():
			elapsed = time()-start
			if elapsed > TIMEOUT*2: break # Just in case the timeout fails
		self.assertAlmostEqual(elapsed, TIMEOUT, delta=1)


# @unittest.skip('skipped')
class GeneralNetworkConnection(unittest.TestCase):
	def setUp(self):
		self.s = TCP_server(HOST,
							EVENT_SOURCE_PORT,
							USER_CLIENT_PORT,
							BUFFER_SIZE,
							timeout=TIMEOUT,
							test_mode=False)
	
	def tearDown(self):
		self.s.stop_server()
		sleep(2) # Allow time for sockets to be releases and threads to terminate
		self.s = None
	
	def test_5_continuous_running(self):
		# Run follower maze twice with no errors. Reset message counter in between
		SEED=666
		EVENTS=1000
		CONCURRENCY=7
		self.s.start_server()
		command = "time java -server -XX:-UseConcMarkSweepGC -Xmx2G -jar ./follower-maze2/FollowerMaze-assembly-1.0.jar {0} {1} {2} > maze.log".format(SEED,EVENTS,CONCURRENCY)
		for i in xrange(2):
			ret = os.system(command)
			self.assertEqual(ret, 0)
			self.s.EP.next_msg = 1
	
	@unittest.skip('skipped')	
	def test_6a_get_connection(self):
		# Test bad port number
		c = self.s.get_connection(HOST, -1)
		self.assertEqual(c, None)
	@unittest.skip('skipped')	
	def test_6b_get_connection(self):
		# Test bad host name
		c = self.s.get_connection('None', USER_CLIENT_PORT)
		self.assertEqual(c, None)


# @unittest.skip('skipped')
class ServerFunctions(unittest.TestCase):
	def setUp(self):
		self.s = TCP_server(HOST,
							EVENT_SOURCE_PORT,
							USER_CLIENT_PORT,
							BUFFER_SIZE,
							timeout=TIMEOUT,
							test_mode=True)
	
	def tearDown(self):
		self.s.stop_server()
		sleep(2)
		self.s = None
	@unittest.skip('skipped')
	def test_8_numerical_arguments(self):
		self.assertRaises(ValueError, TCP_server, HOST, EVENT_SOURCE_PORT, USER_CLIENT_PORT, BUFFER_SIZE, timeout=-1)
		self.assertRaises(ValueError, TCP_server, HOST, EVENT_SOURCE_PORT, USER_CLIENT_PORT, BUFFER_SIZE, maxqueue=0)
		self.assertRaises(ValueError, TCP_server, HOST, EVENT_SOURCE_PORT, USER_CLIENT_PORT, 0)

	@unittest.skip("Skip test 9 as it doesn't run in conjunction with test 10. Both pass indiviually.")
	def test_9_thread_start_point(self):
		# Starting server should introduce 4 new threads
		num_after_init = threading.active_count()
		self.s.start_server()
		sleep(5)
		self.assertEqual(threading.active_count()-num_after_init, 4)
	@unittest.skip('skipped')
	def test_10_stop_server(self):
		# Check no exceptions are raised regardless of connection state
		try:
			self.s.start_server()
			self.s.stop_server()
			self.s.stop_server()
			sleep(2) # wait for exceptions
			result = True
		except:
			result = False
		self.assertTrue(result)
	
	def test_11_add_client(self):
		self.s.add_client(Client(0, None, None))
		self.assertEqual(len(self.s.clients), 1)
		self.s.add_client(Client(0, None, None))
		self.assertEqual(len(self.s.clients), 1)
		
	def test_12_reset_timer(self):
		self.s.TO.start()
		sleep(1)
		self.s.reset_timer()
		after_reset = time()
		self.assertAlmostEqual(self.s.TO.get_last_reset(), after_reset, places=3)


# @unittest.skip('skipped')
class ExtractingDataFromEventBuffer(unittest.TestCase):
	def setUp(self):
		self.s = TCP_server(HOST,
							EVENT_SOURCE_PORT,
							USER_CLIENT_PORT,
							BUFFER_SIZE,
							timeout=TIMEOUT,
							test_mode=True)
	
	def tearDown(self):
		self.s.stop_server()
		self.s = None
	
	def test_13_good_data(self):
		# Check number of messages returned and that they exactly match the buffer
		data = '988|F|46|67\n692|U|46|68\n'
		self.s.event_buffer = data
		msgs = self.s.EP.extract_messages()
		self.assertEqual(len(msgs),2)
		for i in range(2):
			self.assertEqual(msgs[i], data[i*12:(i+1)*12])
	
	def test_14_good_data_plus_incomplete(self):
		# Check number of messages returned and that they exactly match the buffer
		data = '988|F|46|67\n692|U|46|68\nxxx'
		self.s.event_buffer = data
		msgs = self.s.EP.extract_messages()
		self.assertEqual(len(msgs),2)
		self.assertEqual(self.s.event_buffer, 'xxx')
	
	def test_15_no_complete_messages(self):
		# Check that long data is removed and short data is left
		datas = ['xxxxxxxxxxxxxx', 'xxx']
		expected_results = ['', 'xxx']
		for i in range (2):
			self.s.event_buffer = datas[i]
			msgs = self.s.EP.extract_messages()
			self.assertEqual(len(msgs), 0)
			self.assertEqual(self.s.event_buffer, expected_results[i])
	
	def test_16_empty_buffer(self):
		# Check number of messages returned and that buffer is still empty
		self.s.event_buffer = ''
		msgs = self.s.EP.extract_messages()
		self.assertEqual(len(msgs),0)
		self.assertEqual(self.s.event_buffer, '')

# @unittest.skip('skipped')
class ParsingOfIndividualMessages(unittest.TestCase):
	def setUp(self):
		self.s = TCP_server(HOST,
							EVENT_SOURCE_PORT,
							USER_CLIENT_PORT,
							BUFFER_SIZE,
							timeout=TIMEOUT,
							test_mode=True)
	
	def tearDown(self):
		self.s.stop_server()
		self.s = None
	
	def test_17_good_messages(self):
		F,U,B,P,S = '988|F|46|67\n', '692|U|46|68\n', '295|B\n', '992|P|46|68\n', '604|S|46\n'
		
		# F: add follower and attempt to send message
		self.s.EP.process_event(F)
		self.assertEqual(self.s.clients[0].ID, 67)
		self.assertEqual(self.s.clients[0].followers[0], 46)
		
		# U: remove follower
		self.s.add_client(Client(68,None,None))
		self.s.EP.process_event(U)
		self.assertFalse(46 in self.s.clients[1].followers)
		
		# B: Broadcast to all. Just make sure no exceptions thrown.
		self.s.EP.process_event(B)
		
		# P: Private message. Just make sure no exceptions thrown.
		self.s.EP.process_event(P)
		
		# S: Status update. Just make sure no exceptions thrown.
		self.s.clients[0].followers = range(2)
		self.s.EP.process_event(S)
		
	def test_18_bad_messages(self):
		F,U,B,P,S = '988|F|46\n', '692|U|46\n', '295|B|xxx\n', '992|P|46\n', '604|S\n'
		
		# F: to_user_id missing. Check no extra clients are created
		self.s.EP.process_event(F)
		self.assertEqual(len(self.s.clients), 0)
		
		# U: to_user_id missing. Check no exceptions are thrown
		self.s.EP.process_event(U)
		
		# B: Extra data in message. Check no exceptions are thrown
		for i in range(2): self.s.add_client(Client(68,None,None))
		self.s.EP.process_event(B)
		
		# P: to_user_id missing. Check no exceptions are thrown
		self.s.EP.process_event(P)
		
		# S: from_user_id missing. Check no exceptions are thrown
		self.s.EP.process_event(S)
	
	def test_19_unknown_message_type(self):
		bad_msgs = ['0|X|0|0\n', 'xxx|F|yyy|zzz\n']
		for msg in bad_msgs:
			self.s.EP.process_event(msg)


# @unittest.skip('skipped')
class Queue(unittest.TestCase):
	def setUp(self):
		self.this_maxqueue = 10
		self.s = TCP_server(HOST,
							EVENT_SOURCE_PORT,
							USER_CLIENT_PORT,
							BUFFER_SIZE,
							timeout=TIMEOUT,
							test_mode=True,
							maxqueue=self.this_maxqueue)
	
	def tearDown(self):
		self.s.stop_server()
		sleep(2) # Allow time for sockets to be released and threads to terminate
		self.s = None
	
	def test_21_queue_overflow_protection(self):
		# Stuff buffer with artificial data and let the event parser clean it up
		self.s.EP.start()
		for n in range(2,2+self.this_maxqueue):
			self.s.event_buffer += '{0}|X|000|000\n'.format(n)
		self.assertLessEqual(len(self.s.EP.queue), self.this_maxqueue)
		self.s.event_buffer += '2|X|000|000\n'
		self.assertLessEqual(len(self.s.EP.queue), 0)
		
	def test_22_lost_messages_ignored(self):
		# Add message with sequence number less than the due one
		self.s.EP.start()
		self.s.event_buffer += '0|X|000|000\n'
		self.assertLessEqual(len(self.s.EP.queue), 0)


# @unittest.skip('skipped')
class Clients(unittest.TestCase):
	def setUp(self):
		self.s = TCP_server(HOST,
							EVENT_SOURCE_PORT,
							USER_CLIENT_PORT,
							BUFFER_SIZE,
							timeout=TIMEOUT,
							test_mode=True)
	
	def tearDown(self):
		self.s = None
		
	def test_23_sending_fail(self):
		# Add client, pack with fake data and 
		self.s.add_client(Client(0,None,None))
		c = self.s.clients[0]
		c.conn = 'connection'
		c.addr = 'address'
		c.send('message')
		self.assertIsNone(c.conn)
		self.assertIsNone(c.addr)

if __name__ == '__main__':
    unittest.main()

