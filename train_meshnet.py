import copy
import os
import torch
import time
from torch.autograd import Variable
import torch.nn as nn
import torch.optim as optim
import torch.utils.data as data
from tensorboardX import SummaryWriter
import sklearn.metrics
import numpy as np
import torch.backends.cudnn as cudnn

import sys
sys.path.insert(1, './utils/meshnet')
sys.path.insert(1, './models')
sys.path.insert(1, './datasets')
from config import get_train_config
from meshnet_dataset import MeshNetDataset
from meshnet_model import MeshNet
from retrival import append_feature, calculate_map

cfg = get_train_config()
os.environ['CUDA_VISIBLE_DEVICES'] = cfg['cuda_devices']


data_set = {
    x: MeshNetDataset(cfg=cfg['dataset'], part=x) for x in ['train', 'test']
}
data_loader = {
    x: data.DataLoader(data_set[x], batch_size=cfg['batch_size'], num_workers=4, shuffle=True, pin_memory=False)
    for x in ['train', 'test']
}

torch.manual_seed(1)
cudnn.benchmark = False
cudnn.deterministic = True


def train_model(model, criterion, optimizer, scheduler, cfg):

    best_acc = 0.0
    best_map = 0.0
    best_model_wts = copy.deepcopy(model.state_dict())

    from datetime import datetime
    current_time = datetime.now().strftime('%b%d_%H-%M-%S')
    log_dir = os.path.join('runs', current_time)
    writer = SummaryWriter(log_dir+'-bs64_e300')

    for epoch in range(1, cfg['max_epoch'] + 1):

        print('-' * 60)
        print('Epoch: {} / {}'.format(epoch, cfg['max_epoch']))
        print('-' * 60)

        for phrase in ['train', 'test']:

            if phrase == 'train':
                scheduler.step()
                model.train()
            else:
                model.eval()

            running_loss = 0.0
            running_corrects = 0
            ft_all, lbl_all = None, None
            preds_list, labels_list = [], []

            for i, (centers, corners, normals, neighbor_index, targets) in enumerate(data_loader[phrase]):

                optimizer.zero_grad()

                centers = Variable(torch.cuda.FloatTensor(centers.cuda()))
                corners = Variable(torch.cuda.FloatTensor(corners.cuda()))
                normals = Variable(torch.cuda.FloatTensor(normals.cuda()))
                neighbor_index = Variable(torch.cuda.LongTensor(neighbor_index.cuda()))
                targets = Variable(torch.cuda.LongTensor(targets.cuda()))

                with torch.set_grad_enabled(phrase == 'train'):
                    outputs, feas = model(centers, corners, normals, neighbor_index)
                    _, preds = torch.max(outputs, 1)
                    loss = criterion(outputs, targets)
                    preds_list.append(preds.detach().cpu().numpy())
                    labels_list.append(targets.detach().cpu().numpy())

                    if phrase == 'train':
                        loss.backward()
                        optimizer.step()

                    if phrase == 'test':
                        ft_all = append_feature(ft_all, feas.detach().cpu().numpy())
                        lbl_all = append_feature(lbl_all, targets.detach().cpu().numpy(), flaten=True)

                    running_loss += loss.item() * centers.size(0)
                    running_corrects += torch.sum(preds == targets.data)

            epoch_loss = running_loss / len(data_set[phrase])
            epoch_acc = running_corrects.double() / len(data_set[phrase])

            if phrase == 'train':
                print('{} Loss: {:.4f} Acc: {:.4f}'.format(phrase, epoch_loss, epoch_acc))
                writer.add_scalar('data/train_loss', epoch_loss, epoch)
                writer.add_scalar('data/train_acc', epoch_acc, epoch)

            if phrase == 'test':
                epoch_map = calculate_map(ft_all, lbl_all)
                if epoch_acc > best_acc:
                    best_acc = epoch_acc
                    best_model_wts = copy.deepcopy(model.state_dict())
                if epoch_map > best_map:
                    best_map = epoch_map
                if epoch % 10 == 0:
                    torch.save(copy.deepcopy(model.state_dict()), 'ckpt_root/{}.pkl'.format(epoch))

                print('{} Loss: {:.4f} Acc: {:.4f} mAP: {:.4f}'.format(phrase, epoch_loss, epoch_acc, epoch_map))
                clsf_rpt = sklearn.metrics.classification_report(np.concatenate(labels_list, axis=None), np.concatenate(preds_list, axis=None))
                print(clsf_rpt)
                writer.add_scalar('data/test_loss', epoch_loss, epoch)
                writer.add_scalar('data/test_acc', epoch_acc, epoch)

    writer.close()
    return best_model_wts


if __name__ == '__main__':

    model = MeshNet(cfg=cfg['MeshNet'], require_fea=True)
    model.cuda()
    model = nn.DataParallel(model)
    num_total_params = sum(p.numel() for p in model.parameters())
    num_trainable_params = sum(p.numel() for p in model.parameters() if p.requires_grad)
    print('Number of total paramters: %d, number of trainable parameters: %d' % (num_total_params, num_trainable_params))

    criterion = nn.CrossEntropyLoss()
    optimizer = optim.SGD(model.parameters(), lr=cfg['lr'], momentum=cfg['momentum'], weight_decay=cfg['weight_decay'])
    scheduler = optim.lr_scheduler.MultiStepLR(optimizer, milestones=cfg['milestones'], gamma=cfg['gamma'])

    t = time.time()
    best_model_wts = train_model(model, criterion, optimizer, scheduler, cfg)
    t_duration = time.time() - t
    print('total time : {:.3f}s'.format(t_duration))
    print('Number of total paramters: %d' % (num_total_params))
    torch.save(best_model_wts, os.path.join(cfg['ckpt_root'], 'MeshNet_best.pkl'))
