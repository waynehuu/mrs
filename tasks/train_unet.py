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
from mrs_utils import metric_utils


DATA_FILE = r'/hdd/mrs/inria/file_list.txt'
BATCH_SIZE = 16
GPU = 0
ENCODER_NAME = 'res101'
DECODER_NAME = 'unet'
N_CLASS = 2
INIT_LR_ENCODER = 1e-4
INIT_LR_DECODER = 1e-4
MILESTONES = '40'
DROP_RATE = 0.1
EPOCHS = 2
SAVE_DIR = r'/home/lab/Documents/bohao/code/mrs/model/log_pre'
SAVE_EPOCH = 5
PREDIR = r'/home/lab/Documents/bohao/code/ufers/model/log4/model_140.pt'
ALPHA = 0
SEED = 0


def get_unique_name(encoder_name, decoder_name, lre, lrd, ep, ms, alpha):
    return '{}_{}_lre{:.0E}_lrd{:.0E}_ep{}_ms{}_a{}'.format(encoder_name, decoder_name, lre, lrd, ep, ms, alpha)


def read_flag():
    parser = argparse.ArgumentParser()
    parser.add_argument('--data-file', type=str, default=DATA_FILE, help='path to the dataset file')
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
    parser.add_argument('--alpha', type=float, default=ALPHA, help='weight on loss')
    parser.add_argument('--seed', type=int, default=SEED, help='random seed to control reproducibility')

    flags = parser.parse_args()
    home_dir = os.path.join(flags.save_dir, get_unique_name(flags.encoder_name, flags.decoder_name,
                                                            flags.init_lr_encoder, flags.init_lr_decoder,
                                                            flags.epochs, flags.milestones,
                                                            misc_utils.float2str(flags.alpha)))
    flags.log_dir = os.path.join(home_dir, 'log')
    flags.save_dir = home_dir
    flags.milestones = misc_utils.str2list(flags.milestones, sep='_')

    return flags


def main(flags):
    # set label color dict
    label_color_dict = {0: (255, 255, 255), 1: (0, 0, 255), 2: (0, 255, 255), 3: (255, 0, 0),
                        4: (255, 255, 0), 5: (0, 255, 0)}

    # set the random seed
    misc_utils.set_random_seed(flags.seed)

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
    reader = {'train':data_loader.RemoteSensingDataset(file_list=file_list_train,
                                                       transform=transforms['train'], transform_ftr=transforms_ftr['train']),
              'valid':data_loader.RemoteSensingDataset(file_list=file_list_valid,
                                                       transform=transforms['valid'], transform_ftr=transforms_ftr['valid'])}
    reader = {x: data.DataLoader(reader[x], batch_size=flags.batch_size, shuffle=True, num_workers=flags.batch_size,
                                 drop_last=True)
              for x in ['train', 'valid']}

    # build the model
    device = misc_utils.set_gpu(flags.gpu)
    model = unet.Unet(flags.encoder_name, flags.n_class, flags.predir).to(device)

    # make optimizers
    optm = optim.Adam([
        {'params': model.encoder.parameters(), 'lr': flags.init_lr_encoder},
        {'params': model.decoder.parameters(), 'lr': flags.init_lr_decoder}
    ], lr=flags.init_lr_decoder)
    # Decay LR by a factor of drop_rate at each milestone
    scheduler = optim.lr_scheduler.MultiStepLR(optm, milestones=flags.milestones, gamma=flags.drop_rate)

    # define loss function
    criterion = nn.CrossEntropyLoss()
    loss_function = metric_utils.WeightedJaccardCriterion(flags.alpha, criterion)

    # train the model
    start_time = time.time()
    model.train_model(device=device, epochs=flags.epochs, optm=optm, criterion=loss_function,
                      scheduler=scheduler, reader=reader, save_dir=flags.save_dir, summary_path=flags.log_dir,
                      label_color_dict=label_color_dict, rev_transform=inv_normalize, save_epoch=flags.save_epoch)
    duration = time.time() - start_time
    print('Total time: {} hours'.format(duration/60/60))


if __name__ == '__main__':
    flags = read_flag()
    main(flags)
