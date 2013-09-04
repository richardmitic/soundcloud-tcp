soundcloud-tcp

#Soundcloud TCP server challange


Current version 0.1.0

###Testing log
[here](https://docs.google.com/spreadsheet/ccc?key=0AiLh1_T0qNxcdDU0QnJJbnZxUjdCR093XzBvdndGZ1E&usp=sharing)

###Known issues
* Method of stopping the server works but is a bit messy. Needs cleaning up.
* Connections to sockets during the automatic testing are temperamental. Must include long waits to allow the sockets to reset themselves. This cannot be avoided.