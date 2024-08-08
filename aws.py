import boto3
import paramiko
import time
import os
import signal
import sys
import uuid

# Setup your boto3 client
ec2 = boto3.client('ec2', region_name='ap-south-1')

# Define Docker images for each option
docker_images = {
    1: "nginx",  # Option 1: NGINX server
    2: "mysql",  # Option 2: MySQL database
    3: "your-custom-image"  # Option 3: Custom Docker image
}

# Function to select an option
def select_option():
    print("Please select an option:")
    print("1. Launch an NGINX server")
    print("2. Launch a MySQL database")
    print("3. Launch a custom Docker image")

    choice = int(input("Enter your choice (1, 2, or 3): "))

    if choice not in docker_images:
        print("Invalid choice. Please select 1, 2, or 3.")
        return select_option()

    return choice

# Function to create a new key pair and save it to a unique folder
def create_key_pair():
    key_pair_name = 'my-key-pair-' + str(uuid.uuid4())  # Unique key pair name
    key_dir = f'keys/{key_pair_name}'  # Unique folder name

    # Create a directory for the key pair
    os.makedirs(key_dir, exist_ok=True)

    try:
        response = ec2.create_key_pair(KeyName=key_pair_name)
        private_key = response['KeyMaterial']

        key_path = os.path.join(key_dir, f'{key_pair_name}.pem')
        with open(key_path, 'w') as key_file:
            key_file.write(private_key)

        print(f'Private key saved to {key_path}')
        return key_pair_name, key_path
    except Exception as e:
        print(f'Error creating key pair: {e}')
        sys.exit(1)

# Function to launch an EC2 instance
def launch_ec2_instance(key_pair_name):
    response = ec2.run_instances(
        ImageId='ami-0a4408457f9a03be3',  # Replace with your AMI ID
        InstanceType='t2.micro',  # Replace with your instance type
        KeyName=key_pair_name,
        MinCount=1,
        MaxCount=1,
        SecurityGroupIds=['sg-07635eb485deb5057'],  # Replace with your security group ID
        SubnetId='subnet-0c6dd7426c8cefa3f',  # Replace with your subnet ID
    )

    instance_id = response['Instances'][0]['InstanceId']
    print(f'Launched EC2 Instance {instance_id}')

    # Wait for the instance to be running
    waiter = ec2.get_waiter('instance_running')
    waiter.wait(InstanceIds=[instance_id])

    # Get public IP
    instance_info = ec2.describe_instances(InstanceIds=[instance_id])
    public_ip = instance_info['Reservations'][0]['Instances'][0]['PublicIpAddress']

    return instance_id, public_ip

# Function to SSH into the instance and run Docker commands
def run_docker_on_ec2(public_ip, key_file, docker_image):
    key = paramiko.RSAKey.from_private_key_file(key_file)
    ssh_client = paramiko.SSHClient()
    ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    # Wait a few seconds for the instance to be fully ready
    time.sleep(60)

    print(f'Connecting to {public_ip}')
    ssh_client.connect(hostname=public_ip, username='ec2-user', pkey=key)

    # Commands to set up Docker and run the container
    commands = [
        "sudo yum update -y",
        "sudo yum install docker -y",
        "sudo systemctl docker start",
        "sudo usermod -aG docker ec2-user",  # Add ec2-user to docker group
        "sudo systemctl restart docker",  # Apply group changes
        f"docker pull nehal71/candy",
        f"docker run -d candy"  # Run the selected Docker image
    ]

    for command in commands:
        print(f'Running command: {command}')
        stdin, stdout, stderr = ssh_client.exec_command(command)
        print(stdout.read().decode())
        print(stderr.read().decode())

    ssh_client.close()

# Function to terminate the EC2 instance
def terminate_instance(instance_id):
    print(f'Terminating EC2 Instance {instance_id}')
    ec2.terminate_instances(InstanceIds=[instance_id])
    waiter = ec2.get_waiter('instance_terminated')
    waiter.wait(InstanceIds=[instance_id])
    print(f'EC2 Instance {instance_id} terminated')

# Function to delete the key pair and associated files
def delete_key_pair(key_pair_name, key_path):
    print(f'Deleting key pair {key_pair_name}')
    try:
        ec2.delete_key_pair(KeyName=key_pair_name)
        if os.path.exists(key_path):
            os.remove(key_path)
            print(f'Private key file {key_path} deleted')
        else:
            print(f'Private key file {key_path} not found')
    except Exception as e:
        print(f'Error deleting key pair: {e}')

# Function to handle cleanup
def cleanup(instance_id, key_pair_name, key_path):
    terminate_instance(instance_id)
    delete_key_pair(key_pair_name, key_path)

# Setup signal handler for cleanup on exit
def signal_handler(sig, frame):
    print('Received exit signal, performing cleanup...')
    if instance_id:
        cleanup(instance_id, key_pair_name, key_file)
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

# Execute the steps
if __name__ == '__main__':
    choice = select_option()
    docker_image = docker_images[choice]

    key_pair_name, key_file = create_key_pair()

    # Check if the key file was created successfully before proceeding
    if not os.path.exists(key_file):
        print(f'Error: Private key file {key_file} was not created.')
        sys.exit(1)

    instance_id, public_ip = launch_ec2_instance(key_pair_name)
    run_docker_on_ec2(public_ip, key_file, docker_image)

    # Wait for user input to terminate the instance and cleanup
    input("Press Enter to terminate the instance and perform cleanup...")
    cleanup(instance_id, key_pair_name, key_file)

