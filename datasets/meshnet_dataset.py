import numpy as np
import os
import torch
import torch.utils.data as data
import pandas as pd

type_to_index_map = {
    'AD': 0, 'CN': 1
}


class MeshNetDataset(data.Dataset):

    def __init__(self, cfg, part='train', datapath):
        self.root = cfg['data_root']
        self.augment_data = cfg['augment_data']
        self.max_faces = cfg['max_faces']
        self.part = part
        self.datapath = datapath

        df = pd.read_csv(datapath)
        filepaths = df['mesh_fsl']
        dxs = df['dx']

        self.data = []
        for file, dx in zip(filepaths, dxs) :
            _, filename = os.path.split(file)
            filename = self.root + '/' + filename.split('.')[0] + '.npz'
            self.data.append(filename, type_to_index_map[dx])

    def __getitem__(self, i):
        path, type = self.data[i]
        data = np.load(path)
        face = data['faces']
        neighbor_index = data['neighbors']

        # data augmentation
        if self.augment_data and self.part == 'train':
            sigma, clip = 0.01, 0.05
            jittered_data = np.clip(sigma * np.random.randn(*face[:, :12].shape), -1 * clip, clip)
            face = np.concatenate((face[:, :12] + jittered_data, face[:, 12:]), 1)

        # fill for n < max_faces with randomly picked faces
        num_point = len(face)
        if num_point < self.max_faces:
            fill_face = []
            fill_neighbor_index = []
            for i in range(self.max_faces - num_point):
                index = np.random.randint(0, num_point)
                fill_face.append(face[index])
                fill_neighbor_index.append(neighbor_index[index])
            face = np.concatenate((face, np.array(fill_face)))
            neighbor_index = np.concatenate((neighbor_index, np.array(fill_neighbor_index)))

        # to tensor
        face = torch.from_numpy(face).float()
        neighbor_index = torch.from_numpy(neighbor_index).long()
        target = torch.tensor(type, dtype=torch.long)

        # reorganize
        face = face.permute(1, 0).contiguous()
        centers, corners, normals = face[:3], face[3:12], face[12:]
        corners = corners - torch.cat([centers, centers, centers], 0)

        return centers, corners, normals, neighbor_index, target

    def __len__(self):
        return len(self.data)

