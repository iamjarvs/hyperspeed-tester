import os
import socket
import ftplib
import sys
import hashlib
import json
import shutil
import time
import requests
import python_arptable
import subprocess32 as subprocess
import netifaces
import speedtest
import signal
import time
import random
from python_arptable import get_arp_table
from uuid import getnode as get_mac
from paramiko import SSHClient
import paramiko
from scp import SCPClient

##Set the hostname of the iperf server to perform tests againsts
hostname = "X.X.X.X"
log_files = "/home/iperf"

#Define global variables
sent_gbps = ""
received_gbps = ""
peak = ""


##Function displays the TopLine and BottomLine message passed on the screen
def ScreenOutput(TopLine, BottomLine):
    print TopLine + " " + BottomLine

##Create a function that will raise a timeout error when called
def timeout_handler(num, stack):
    raise Exception("timed_out")
    
##Function performs a ping test against the server to ensure that it is accessible
def pingHome():
    ScreenOutput('Ping Test', 'Executing...')
    time.sleep(1)
    ##Perform an OS command to execute the ping test
    response = os.system("ping -c 2 " + hostname)
    status = ""

    ##Check the result to see whether the pings were successful
    if response == 0:
      status = True
      ScreenOutput('Ping Test', 'Succesful')
      time.sleep(1)
    else:
      status = False
      ScreenOutput('Ping Test', 'Unsuccessful')
      time.sleep(3)
    return status

##Function performs a test against the FTP socket to ensure the FTP service is accessible on the server
def testSCPSocket() :
    #check ftp is running on the host by established a socket on port 21. Set the timeout for the socket to 3 seconds
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(3)
    result = sock.connect_ex((hostname, 22))
    ##Closes the socket to ensure the connection is closed
    sock.shutdown(socket.SHUT_RDWR)
    sock.close()
    ##Check whether the socket could connect successfully
    if result == 0:
        ScreenOutput('SFTP Test', 'Succesful')
        time.sleep(1)
        return True
    else:
        ScreenOutput('SFTP Test', 'Unsuccessful')
        time.sleep(3)
        ScreenOutput('Test Failed', 'Retrying...')
        time.sleep(1)
        ##Rerun the test if the FTP socket fails
        executeTesting()
        return False

def randomPortNumber():
    randomPort = random.randint(5201,5251)
    return randomPort

##Function performs a check against the default IPerf port 5201 to ensure it is up
def testIperfSocket(randomPort) :
    #check iperf is running on the host by establishing the socket the port 5201
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(3)
    result = sock.connect_ex((hostname, randomPort))
    if result == 0:
        sock.shutdown(socket.SHUT_RDWR)
        ##Close the socket otherwise the server thinks a test is still occurring which prevents any further tests
        sock.close()
        ScreenOutput('Iperf Connection', 'Succesful')
        time.sleep(1)
        return True
    else:
        ScreenOutput('Iperf Connection', 'Unsuccessful')
        time.sleep(3)
        ScreenOutput('Test Failed', 'Retrying...')
        time.sleep(1)
        ##Rerun the test if the IPerf connection fails
        executeTesting()
        return False


def copySCPfiles(hashed_file_name):
    try:
        ScreenOutput("Copying Test", "To Server")
        time.sleep(3)
        hashed_file_path = log_files + "/" + hashed_file_name
        ssh = SSHClient()
        ssh.load_system_host_keys()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(hostname, username="username")
        scp = SCPClient(ssh.get_transport())
        scp.put(hashed_file_path, hashed_file_path)
        scp.close()
        ScreenOutput('Test Copied', 'To Server')
        time.sleep(1)
    except Exception, e:
        ScreenOutput("Copy To", "Server Failed")
        time.sleep(3)
        ScreenOutput("Restarting", "Speed Test")
        time.sleep(2)
        executeTesting()

##Function will obtain the default gateway MAC address
def get_dg_mac():
    ##Grab the default gateway address
    gws = netifaces.gateways()
    gateway_address_list = gws['default'][netifaces.AF_INET]
    gateway_address = gateway_address_list[0]

    ##Import the contents of the ARP table for reading
    arp_table = get_arp_table()
    ##Loop through each ARP entry to check whether the gateway address is present
    for arp_entry in arp_table:
        if arp_entry["IP address"] == gateway_address:
            ##Grab the MAC address associated with the gateway address
            gateway_mac = arp_entry["HW address"]

    return gateway_mac

##Function will perform another speed test as well for comparison using Ookla's speedtest.net
def perform_ookla_test():
    servers = []
    ScreenOutput("Performing Ookla", "Speedtest...")
    ookla = speedtest.Speedtest()
    ookla.get_servers(servers)
    ookla.get_best_server()
    ookla_download = ookla.download() / 1000000
    ookla_upload = ookla.upload() / 1000000
    ookla_array = {}
    ookla_array["download"] = ookla_download
    ookla_array["upload"] = ookla_upload
    return ookla_array

##Function will take the returned JSON and append new required values on the end
def edit_json(hashed_file_name, gateway_mac) :
    ##Open the file and read the contents
    file_path = log_files + "/" + hashed_file_name
    f = open(file_path, 'r')
    file_contents = f.read()
    f.close()

    ##Grab the IP address of the CPE device
    url_to_send = "http://" + hostname + ":6729/whats-my-ip"
    try:
        json_ip_address = requests.get(url_to_send).json()
        gateway_ip = json_ip_address["ip"]
    except:
        gateway_ip = "Unknown"

    ##Perform an Ookla Speedtest with a 20 second timeout
    ookla_results = {}
    signal.signal(signal.SIGALRM, timeout_handler)
    signal.alarm(20)
    try:
        ookla_results = perform_ookla_test()
    except Exception as ex:
        if "timed_out" in ex:
            ookla_results["download"] = ""
            ookla_results["upload"] = ""
        else:
            ookla_results["download"] = ""
            ookla_results["upload"] = ""
    finally:
        signal.alarm(0)
     
    ##Obtain the MAC address of the board
    board_mac = get_mac()
    ##Format the MAC address into a common form
    formatted_board_mac = str(':'.join(("%012X" % board_mac)[i:i+2] for i in range(0, 12, 2)))

    ##Load in the contents of the file and convert to a JSON object
    json_file_contents = json.loads(file_contents)
    ##Add the new JSON values onto the end, the boards MAC address, the file hash, and the gateway MAC
    json_file_contents["end"]["host_information"] = {"mac_address": formatted_board_mac, "hash": hashed_file_name, "gateway_mac": gateway_mac, "gateway_ip": gateway_ip}
    json_file_contents["end"]["ookla_test"] = {"download": ookla_results["download"], "upload": ookla_results["upload"]}
    
    ##Dump the new JSON information into the file
    json.dump(json_file_contents, open(file_path, "w"))
    
    

##Function will run the Line Test
def runTest(randomPort) :
    global sent_gbps
    global received_gbps
    global hostname
    global peak

    ScreenOutput('Speed Test', 'Executing...')
    time.sleep(1)

    ##Try and execute the IPerf test. Specifies a timeout of 14 seconds for the IPerf connection
    try:
        procId = subprocess.run(["iperf3","-c", hostname, "-J", "-t", "15", "-p", randomPort], stdout=subprocess.PIPE, timeout=30)
    ##Raise an error if the timeout expires and re-run the test
    except subprocess.TimeoutExpired:
        ScreenOutput('Speed Test', 'Failed')
        time.sleep(3)
        executeTesting()
    ##Take the stdout and convert to JSON from the executed command
    json_output = procId.stdout

    ##Write the JSON to the file
    f = open(log_files + '/results.json', 'w+')
    string_to_write = str(json_output)
    f.write(string_to_write)
    f.close()

    file_name = log_files + "/results.json"

    ##Open the JSON file just created
    with open(file_name) as json_data:
        jdata = json.load(json_data)

    ##Check to see whether the JSON entered into the file is from a successful test and not a server
    ##busy message
    try:
        ##Extract the sent and received BPS for screen output
        sent_bps = jdata['end']['sum_sent']['bits_per_second']
        received_bps =  jdata['end']['sum_received']['bits_per_second']
        counter = 0
        speed_interval_list = list()
        for x in jdata["intervals"]:
            var = jdata['intervals'][counter]['sum']['bits_per_second']
            speed_interval_list.append(var)
            counter = counter+1
        peak = max(speed_interval_list)
        peak = peak / 1000000

    ##Display the error if the server is busy if the JSON is not complete
    except:
        ScreenOutput('Server Busy', 'Retrying')
        time.sleep(3)
        ##Rerun the test again
        executeTesting()

    ##Convert the bps into gbps
    sent_gbps = sent_bps / 1000000
    received_gbps = received_bps / 1000000
    ScreenOutput('Speed Test', 'Finished')
    time.sleep(1)

    ##Read in the contents of the file in order to generate a hash of the data
    with open(file_name) as file_to_hash:
        data = file_to_hash.read()
        md5_hash = hashlib.md5(data).hexdigest()

    ##Take the last 10 characters from the hash to make it shorter
    hash_name = md5_hash[:10]
    new_hash_name = log_files + "/" + hash_name.upper()
    ##Rename the file from results.json to the generated hash to uniquely identify the hash
    shutil.move(log_files + "/results.json", new_hash_name)

    lowerHash = md5_hash[:10]
    ##Convert the hash to uppercase for nicer viewing
    upperHash = lowerHash.upper()

    return upperHash

##Function actually conducts the test and performs the checks
def executeTesting():
    global sent_gbps
    global received_gbps
    global peak

    ##Display that the test is starting
    ScreenOutput('Starting', 'Speed Test')
    time.sleep(2)
    ##Execute the PingHome function in order to check whether there is connectivity to the IPerf Server
    connectionStatus = pingHome()

    if connectionStatus == True :
        ##Check whether there is connectivity to the FTP port
        #testFtpSocket()
        testSCPSocket()
        ##Check whether there is connectivity to the IPerf Server on port 5201 for the IPerf test
        
        #####################Add random socket here
        randomPort = randomPortNumber()

        testIperfSocket(int(randomPort))
        ##Obtain the hash of the file received from executing the test
        hash_file = runTest(int(randomPort))
        ##Obtain the MAC address of the current gateway
        gateway_mac = get_dg_mac()
        ##Change the JSON file created to include the extra data including gateway MAC, board MAC, and hash
        edit_json(hash_file, gateway_mac)
        ##Call the function that will copy the test file specified by the hash to the IPerf Server
        #copyftpfiles(hash_file)
        copySCPfiles(hash_file)
        ##Display the test case ID which is equal to the hash
        ScreenOutput('Test ID', hash_file)
        time.sleep(5)
        ##Display the upload speed extracted from the JSON file
        ScreenOutput('Upload:', str(round(sent_gbps, 2)) + " Mbps" )
        time.sleep(2)
        ##Display the download speed extracted from the JSON file
        ScreenOutput('Download:', str(round(received_gbps, 2)) + " Mbps")
        time.sleep(2)
        ##Display the download speed extracted from the JSON file
        ScreenOutput('Peak:', str(round(peak, 2)) + " Mbps")
        time.sleep(2)
    else:
        ##If the ping test fails meaning no connectivity to the IPerf server then restart the test again
        ScreenOutput('Test Failed', 'Retrying...')
        time.sleep(3)
        executeTesting()
##Execute the Line Test for the first time
executeTesting()
