import yaml


def GenerateFirewall(context):
    name = context.env['deployment'] + '-opscenterfirewall-' + context.env['name']
    firewalls = [
        {
            'name': name,
            'type': 'compute.v1.firewall',
            'properties': {
                'sourceRanges': [
                    '0.0.0.0/0'
                ],
                'allowed': [{
                    'IPProtocol': 'tcp',
                    'ports': ['8888', '8443']
                }]
            }
        }
    ]

    return firewalls


def GenerateReferencesList(context):
    reference_list = []
    n_of_copies = context.properties['nodesPerZone']
    dep_name = context.env['deployment']
    for zone in context.properties['zones']:
        for idx in range(1, n_of_copies + 1):
            node_name = '$(ref.' + dep_name + '-' + zone + '-' + str(idx) + '-vm' + '.selfLink)'
            reference_list.append(node_name)
    return ' '.join(reference_list)


def GenerateConfig(context):
    config = {'resources': []}

    seed_nodes_dns_names = context.env['deployment'] + '-' + context.properties['zones'][0] + '-1-vm.c.' + context.env['project'] + '.internal'

    dse_node_script = '''
        #!/usr/bin/env bash

        mkdir /mnt
        /usr/share/google/safe_format_and_mount -m "mkfs.ext4 -F" /dev/disk/by-id/google-${HOSTNAME}-data-disk /mnt

        wget https://github.com/DSPN/install-datastax/archive/master.zip
        apt-get -y install unzip
        unzip master.zip
        cd install-datastax-master/bin

        cloud_type="google"
        zone=$(curl -s -H "Metadata-Flavor: Google" "http://metadata.google.internal/computeMetadata/v1/instance/zone" | grep -o [[:alnum:]-]*$)
        data_center_name=$zone
        seed_nodes_dns_names=''' + seed_nodes_dns_names + '''

        echo "Configuring nodes with the settings:"
        echo cloud_type $cloud_type
        echo seed_nodes_dns_names $seed_nodes_dns_names
        echo data_center_name $data_center_name
        ./dse.sh $cloud_type $seed_nodes_dns_names $data_center_name
        '''

    zonal_clusters = {
        'name': 'clusters-' + context.env['name'],
        'type': 'regional_multi_vm.py',
        'properties': {
            'sourceImage': 'https://www.googleapis.com/compute/v1/projects/datastax-public/global/images/datastax-ubuntu1404-img-03172016',
            'zones': context.properties['zones'],
            'machineType': context.properties['machineType'],
            'network': 'default',
            'numberOfVMReplicas': context.properties['nodesPerZone'],
            'disks': [
                {
                    'deviceName': 'vm-data-disk',
                    'type': 'PERSISTENT',
                    'boot': 'false',
                    'autoDelete': 'true',
                    'initializeParams': {
                        'diskType': 'pd-ssd',
                        'diskSizeGb': context.properties['diskSize']
                    }
                }
            ],
            'bootDiskType': 'pd-standard',
            'metadata': {
                'items': [
                    {
                        'key': 'startup-script',
                        'value': dse_node_script
                    }
                ]
            }
        }
    }

    ops_center_script = '''
      #!/usr/bin/env bash

      wget https://github.com/DSPN/install-datastax/archive/master.zip
      apt-get -y install unzip
      unzip master.zip
      cd install-datastax-master/bin

      cloud_type="google"
      seed_nodes_dns_names=''' + seed_nodes_dns_names + '''
      echo "Configuring nodes with the settings:"
      echo cloud_type $cloud_type
      echo seed_nodes_dns_names $seed_nodes_dns_names
      ./opscenter.sh $cloud_type $seed_nodes_dns_names
    '''

    ops_center_node = {
        'name': context.env['deployment'] + '-opscenter-' + context.env['name'],
        'type': 'vm_instance.py',
        'properties': {
            'sourceImage': 'https://www.googleapis.com/compute/v1/projects/datastax-public/global/images/datastax-ubuntu1404-img-03172016',
            'zone': context.properties['opsCenterZone'],
            'machineType': context.properties['machineType'],
            'network': 'default',
            'bootDiskType': 'pd-standard',
            'serviceAccounts': [{
                'email': 'default',
                'scopes': ['https://www.googleapis.com/auth/compute']
            }],
            'metadata': {
                'items': [
                    {
                        'key': 'startup-script',
                        'value': ops_center_script
                    },
                    {
                        'key': 'bogus-references',
                        'value': GenerateReferencesList(context)
                    }
                ]
            }
        }
    }

    config['resources'].append(zonal_clusters)
    config['resources'].append(ops_center_node)
    config['resources'].extend(GenerateFirewall(context))

    return yaml.dump(config)
