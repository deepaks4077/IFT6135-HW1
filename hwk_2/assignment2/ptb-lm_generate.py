import time
import collections
import os
import sys
import torch
import torch.nn
from torch.autograd import Variable
import torch.nn as nn
import numpy as np

from models import RNN, GRU
from models import make_model as TRANSFORMER

# HELPER FUNCTIONS


def _read_words(filename):
    with open(filename, "r") as f:
        return f.read().replace("\n", "<eos>").split()


def _build_vocab(filename):
    data = _read_words(filename)

    counter = collections.Counter(data)
    count_pairs = sorted(counter.items(), key=lambda x: (-x[1], x[0]))

    words, _ = list(zip(*count_pairs))
    word_to_id = dict(zip(words, range(len(words))))
    id_to_word = dict((v, k) for k, v in word_to_id.items())

    return word_to_id, id_to_word


def _file_to_word_ids(filename, word_to_id):
    data = _read_words(filename)
    return [word_to_id[word] for word in data if word in word_to_id]

# Processes the raw data from text files


def ptb_raw_data(data_path=None, prefix="ptb"):
    train_path = os.path.join(data_path, prefix + ".train.txt")
    valid_path = os.path.join(data_path, prefix + ".valid.txt")
    test_path = os.path.join(data_path, prefix + ".test.txt")

    word_to_id, id_2_word = _build_vocab(train_path)
    train_data = _file_to_word_ids(train_path, word_to_id)
    valid_data = _file_to_word_ids(valid_path, word_to_id)
    test_data = _file_to_word_ids(test_path, word_to_id)
    return train_data, valid_data, test_data, word_to_id, id_2_word

# Yields minibatches of data


def ptb_iterator(raw_data, batch_size, num_steps):
    raw_data = np.array(raw_data, dtype=np.int32)

    data_len = len(raw_data)
    batch_len = data_len // batch_size
    data = np.zeros([batch_size, batch_len], dtype=np.int32)
    for i in range(batch_size):
        data[i] = raw_data[batch_len * i:batch_len * (i + 1)]

    epoch_size = (batch_len - 1) // num_steps

    if epoch_size == 0:
        raise ValueError("epoch_size == 0, decrease batch_size or num_steps")

    for i in range(epoch_size):
        x = data[:, i * num_steps:(i + 1) * num_steps]
        y = data[:, i * num_steps + 1:(i + 1) * num_steps + 1]
        yield (x, y)


class Batch:
    "Data processing for the transformer. This class adds a mask to the data."

    def __init__(self, x, pad=-1):
        self.data = x
        self.mask = self.make_mask(self.data, pad)

    @staticmethod
    def make_mask(data, pad):
        "Create a mask to hide future words."

        def subsequent_mask(size):
            """ helper function for creating the masks. """
            attn_shape = (1, size, size)
            subsequent_mask = np.triu(np.ones(attn_shape), k=1).astype('uint8')
            return torch.from_numpy(subsequent_mask) == 0

        mask = (data != pad).unsqueeze(-2)
        mask = mask & Variable(
            subsequent_mask(data.size(-1)).type_as(mask.data))
        return mask


# LOAD DATA
print('Loading data from ' + 'data')
raw_data = ptb_raw_data(data_path='data')
train_data, valid_data, test_data, word_to_id, id_2_word = raw_data
vocab_size = len(word_to_id)
print('  vocabulary size: {}'.format(vocab_size))


def load_model(model_type, device, seq_len=35, batch_size=20, hidden_size=1500, num_layers=2, saved_model=None):
    if model_type == 'RNN':
        model = RNN(emb_size=200, hidden_size=1500,
                    seq_len=seq_len, batch_size=batch_size,
                    vocab_size=vocab_size, num_layers=2,
                    dp_keep_prob=0.35)
    if model_type == 'GRU':
        model = GRU(emb_size=200, hidden_size=1500,
                    seq_len=seq_len, batch_size=batch_size,
                    vocab_size=vocab_size, num_layers=2,
                    dp_keep_prob=0.35)
    model = model.to(device)

    if saved_model is not None:
        model.load_state_dict(torch.load(saved_model, map_location=device))
    return model


# Use the GPU if you have one
use_gpu = 0
if torch.cuda.is_available():
    print("Using the GPU")
    device = torch.device("cuda")
    use_gpu = 1
else:
    print("WARNING: You are about to run on cpu, and this will likely run out \
      of memory. \n You can try setting batch_size=1 to reduce memory usage")
    device = torch.device("cpu")


def generate_samples(model_type, saved_model_path, generated_seq_len, num_samples, hidden_size, num_layers):
    # initial token
    x = np.random.choice(vocab_size, (1, num_samples))
    inputs = torch.from_numpy(x.astype(np.int64)).transpose(0, 1).contiguous().to(device)
    model = load_model(model_type, device, seq_len=generated_seq_len, batch_size=num_samples, hidden_size=hidden_size,
                       num_layers=num_layers, saved_model=saved_model_path)
    model.eval()
    model.zero_grad()
    hidden = model.init_hidden().to(device)
    gen_samples = model.generate(inputs, hidden, generated_seq_len - 1)
    if use_gpu == 1:
        sample_words = [' '.join([id_2_word[t] for t in seq]) for seq in gen_samples.cpu().numpy().T]
    else:
        sample_words = [' '.join([id_2_word[t] for t in seq]) for seq in gen_samples.numpy().T]
    return sample_words



# RNN
model_type = "GRU"
# use the model from 4.1
# saved_model_path = "4.1_exp/RNN_ADAM_model=RNN_optimizer=ADAM_initial_lr=0.0001_batch_size=20_seq_len=35_hidden_size=1500_num_layers=2_dp_keep_prob=0.35_save_best_0/best_params.pt"

# use of one the improved models from 4.3
# saved_model_path = "4.3_exp/improved/RNN_ADAM_model=RNN_optimizer=ADAM_initial_lr=0.0001_batch_size=20_seq_len=50_hidden_size=1500_num_layers=2_dp_keep_prob=0.35_save_best_0/best_params.pt"

# use one of the improved models from 4.3
# saved_model_path = "4.3_exp/improved/RNN_ADAM_model=RNN_optimizer=ADAM_initial_lr=0.0001_batch_size=40_seq_len=35_hidden_size=1500_num_layers=2_dp_keep_prob=0.35_save_best_0/best_params.pt"

# use one of the improved models from 4.3
# saved_model_path = "4.3_exp/improved/RNN_ADAM_model=RNN_optimizer=ADAM_initial_lr=0.0001_batch_size=30_seq_len=50_hidden_size=1500_num_layers=2_dp_keep_prob=0.35_save_best_0/best_params.pt"
saved_model_path = "GRU/best_params.pt"

num_samples = 10
generated_seq_len = 35
hidden_size = 1500
num_layers = 2
RNN_samples_1 = generate_samples(model_type, saved_model_path, generated_seq_len, num_samples, hidden_size, num_layers)
for i in RNN_samples_1:
    print(i + "\n")
