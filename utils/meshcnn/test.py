import numpy as np
import sklearn.metrics

import sys
sys.path.insert(1, './utils/meshcnn')
sys.path.insert(1, './models')
sys.path.insert(1, './datasets')
from test_options import TestOptions
from meshcnn_dataset import DataLoader
from meshcnn_model import ClassifierModel
from writer import Writer

def run_test(datapath, epoch=-1):
    print('Running Test')
    opt = TestOptions().parse()
    opt.serial_batches = True  # no shuffle
    dataset = DataLoader(opt, datapath)
    model = ClassifierModel(opt)
    writer = Writer(opt)
    # test
    writer.reset_counter()
    heappop_error_test = 0
    pred_classes = []
    label_classes = []
    for i, data in enumerate(dataset):
        model.set_input(data)
        if opt.dataset_mode == 'classification' :
            try :
                ncorrect, nexamples, pred_class, label_class = model.test()
                pred_classes.append(pred_class.cpu().numpy())
                label_classes.append(label_class.cpu().numpy())
                #print(sklearn.metrics.classification_report(np.concatenate(label_classes, axis=None), np.concatenate(pred_classes, axis=None)))
                writer.update_counter(ncorrect, nexamples)
            except IndexError:
                heappop_error_test += 1
                print('(%d) IndexError occured, passed to next data' % (heappop_error_test))
                pass
        else :
            ncorrect, nexamples, pred_class, label_class = model.test()
            writer.update_counter(ncorrect, nexamples)
        
    writer.print_acc(epoch, writer.acc)
    if opt.dataset_mode == 'classification' :
        print(sklearn.metrics.classification_report(np.concatenate(label_classes, axis=None), np.concatenate(pred_classes, axis=None)))
    return writer.acc


if __name__ == '__main__':
    run_test()
