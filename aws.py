import boto3
import paramiko
import time
import os

# Setup your boto3 client
ec2 = boto3.client('ec2', region_name='ap-south-1')

# 1. Define Docker images for each option
docker_images = {
    1: "nginx",  # Option 1: NGINX server
    2: "mysql",  # Option 2: MySQL database
    3: "your-custom-image"  # Option 3: Custom Docker image
}

# 2. Function to select an option
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

# 3. Launch an EC2 instance
def launch_ec2_instance():
    response = ec2.run_instances(
        ImageId='ami-0a4408457f9a03be3',  # Replace with your AMI ID
        InstanceType='t2.micro',  # Replace with your instance type
        KeyName='Jenkins_Private_Key',  # Replace with your key pair name (without .pem extension)
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

# 4. Create a key pair and save it to a file
def create_key_pair():
    key_pair_name = 'Jenkins_Private_Key'
    key_file = f'keys/{key_pair_name}.pem'

    # Create a new key pair
    response = ec2.create_key_pair(KeyName=key_pair_name)
    key_material = response['KeyMaterial']

    # Save the key material to a file
    if not os.path.exists('keys'):
        os.makedirs('keys')

    with open(key_file, 'w') as file:
        file.write(key_material)

    # Set file permissions
    os.chmod(key_file, 0o400)

    return key_pair_name, key_file

# 5. SSH into the instance and run Docker commands
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
        "sudo service docker start",
        "sudo usermod -aG docker ec2-user",  # Add ec2-user to docker group
        "echo 'ec2-user ALL=(ALL) NOPASSWD: /usr/bin/docker' | sudo tee /etc/sudoers.d/docker",  # Grant passwordless sudo for Docker
        "sudo systemctl restart docker",  # Restart Docker to ensure group changes are applied
        f"sudo docker pull nehal71/candy",
        f"sudo docker run -d candy"  # Run the selected Docker image
    ]

    for command in commands:
        print(f'Running command: {command}')
        stdin, stdout, stderr = ssh_client.exec_command(command)
        print(stdout.read().decode())
        print(stderr.read().decode())

    ssh_client.close()

# 6. Terminate the EC2 instance and delete the key pair
def cleanup(instance_id, key_pair_name, key_file):
    # Terminate the EC2 instance
    ec2.terminate_instances(InstanceIds=[instance_id])
    print(f'Terminating EC2 Instance {instance_id}')

    # Delete the key pair
    ec2.delete_key_pair(KeyName=key_pair_name)
    print(f'Deleting Key Pair {key_pair_name}')

    # Remove the key file
    if os.path.exists(key_file):
        os.remove(key_file)
        print(f'Removed Key File {key_file}')

# 7. Execute the steps
if __name__ == '__main__':
    choice = select_option()
    docker_image = docker_images[choice]

    key_pair_name, key_file = create_key_pair()
    instance_id, public_ip = launch_ec2_instance()

    run_docker_on_ec2(public_ip, key_file, docker_image)

    # Cleanup resources
    cleanup(instance_id, key_pair_name, key_file)
