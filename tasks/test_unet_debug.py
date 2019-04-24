"""

"""


# Built-in
import os
import time
import argparse

# Libs
import torchvision
import torch.nn as nn
import torch.optim as optim
from torch.utils import data

# Own modules
from model import unet
from data import data_loader
from mrs_utils import misc_utils
from mrs_utils import xval_utils


DATA_FILE = r'/hdd/mrs/inria/file_list.txt'
INPUT_SIZE = 224
BATCH_SIZE = 8
GPU = 0
ENCODER_NAME = 'res101'
DECODER_NAME = 'unet'
N_CLASS = 2
INIT_LR_ENCODER = 1e-5
INIT_LR_DECODER = 1e-5
MILESTONES = '20_30'
DROP_RATE = 0.1
EPOCHS = 40
SAVE_DIR = r'/home/lab/Documents/bohao/code/mrs/model/log_pre'
SAVE_EPOCH = 1
PREDIR = None # r'/home/lab/Documents/bohao/code/ufers/model/model3.pt'


def get_unique_name(encoder_name, decoder_name, lre, lrd, ep, ms):
    return '{}_{}_lre{:.0E}_lrd{:.0E}_ep{}_ms{}'.format(encoder_name, decoder_name, lre, lrd, ep, ms)



def read_flag():
    parser = argparse.ArgumentParser()
    parser.add_argument('--data-file', type=str, default=DATA_FILE, help='path to the dataset file')
    parser.add_argument('--input-size', type=int, default=INPUT_SIZE, help='input size of the patches')
    parser.add_argument('--batch-size', type=int, default=BATCH_SIZE, help='batch size in training')
    parser.add_argument('--gpu', type=int, default=GPU, help='which gpu to use')
    parser.add_argument('--encoder-name', type=str, default=ENCODER_NAME, help='which encoder to use for extractor, '
                                                                               'see model/model.py for more details')
    parser.add_argument('--decoder-name', type=str, default=DECODER_NAME, help='which decoder style to use')
    parser.add_argument('--n-class', type=int, default=N_CLASS, help='#classes in the output')
    parser.add_argument('--init-lr-encoder', type=float, default=INIT_LR_ENCODER, help='initial learning rate for encoder')
    parser.add_argument('--init-lr-decoder', type=float, default=INIT_LR_DECODER, help='initial learning rate for decoder')
    parser.add_argument('--milestones', type=str, default=MILESTONES, help='milestones for multi step lr drop')
    parser.add_argument('--drop-rate', type=float, default=DROP_RATE, help='drop rate at each milestone in scheduler')
    parser.add_argument('--epochs', type=int, default=EPOCHS, help='num of epochs to train')
    parser.add_argument('--save-dir', type=str, default=SAVE_DIR, help='path to save the model')
    parser.add_argument('--save-epoch', type=int, default=SAVE_EPOCH, help='model will be saved every #epochs')
    parser.add_argument('--predir', type=str, default=PREDIR, help='path to pretrained encoder')

    flags = parser.parse_args()
    home_dir = os.path.join(flags.save_dir, get_unique_name(flags.encoder_name, flags.decoder_name,
                                                            flags.init_lr_encoder, flags.init_lr_decoder,
                                                            flags.epochs, flags.milestones))
    flags.log_dir = os.path.join(home_dir, 'log')
    flags.save_dir = os.path.join(home_dir, 'model.pt')
    flags.milestones = misc_utils.str2list(flags.milestones, sep='_')

    return flags


def main(flags):
    # prepare data reader
    transforms = {
        'train': data_loader.JointCompose([
            data_loader.JointFlip(),
            data_loader.JointRotate(),
            data_loader.JointToTensor(),
        ]),
        'valid': data_loader.JointCompose([
            data_loader.JointToTensor(),
        ]),
    }
    transforms_ftr = {
        'train': torchvision.transforms.Compose({
            torchvision.transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
        }),
        'valid': torchvision.transforms.Compose({
            torchvision.transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
        }),
    }
    inv_normalize = torchvision.transforms.Normalize(
        mean=[-0.485 / 0.229, -0.456 / 0.224, -0.406 / 0.225],
        std=[1 / 0.229, 1 / 0.224, 1 / 0.255]
    )

    file_list = misc_utils.load_file(flags.data_file)
    city_id_list = xval_utils.get_inria_city_id(file_list)
    file_list_train, file_list_valid = xval_utils.split_by_id(file_list, city_id_list, list(range(6)))
    reader = {'train':data_loader.RemoteSensingDataset(file_list=file_list_train, input_size=flags.input_size,
                                                       transform=transforms['train'], transform_ftr=transforms_ftr['train']),
              'valid':data_loader.RemoteSensingDataset(file_list=file_list_valid, input_size=flags.input_size,
                                                       transform=transforms['valid'], transform_ftr=transforms_ftr['valid'])}
    reader = {x: data.DataLoader(reader[x], batch_size=flags.batch_size, shuffle=True, num_workers=flags.batch_size,
                                 drop_last=True)
              for x in ['train', 'valid']}

    # build the model
    import torch
    device = misc_utils.set_gpu(flags.gpu)
    model = unet.Unet(flags.encoder_name, flags.n_class, flags.predir).to(device)
    model.load_state_dict(torch.load(r'/home/lab/Documents/bohao/code/mrs/model/log_pre/res101_unet_lre1E-05_lrd1E-05_ep40_ms40/model_39.pt'))

    import torch.nn
    import numpy as np
    import matplotlib.pyplot as plt
    model.eval()
    for ftr, lbl in reader['valid']:
        ftr = ftr.to(device)
        sf = torch.nn.Softmax(dim=1)
        pred = sf(model.forward(ftr)).data.cpu().numpy()
        pred = np.transpose(pred, (0, 2, 3, 1))
        print(pred.shape)
        for i in range(8):
            plt.imshow(pred[i, : ,: , -1])
            plt.colorbar()
            plt.show()

            plt.imshow(np.argmax(pred[i, :, :, :], axis=-1))
            plt.show()


if __name__ == '__main__':
    flags = read_flag()
    main(flags)