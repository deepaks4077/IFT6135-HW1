# -*- coding: utf-8 -*-

__authors__ = ["Deepak Sharma"]

from typing import Tuple, List, Union, Dict
import argparse
import numpy as np
import os
import math
import torch
from torch.functional import F
import torch.utils.data as data_utils
from torch import nn, optim
from torch.nn import functional as F
from torchvision import datasets, transforms
from torchvision.datasets import utils
from torch.distributions import Normal, Bernoulli
from torchvision.utils import save_image
from torch import autograd

parser = argparse.ArgumentParser(description='VAE with a Bernoulli likelihood')
parser.add_argument('--batch-size', type=int, default=100,
                    help='input batch size for training (default: 100)')
parser.add_argument('--model-filename-prefix', type=str, default="torch_new_bb",
                    help='path to save the model params  (default: torch_new_bb)')
parser.add_argument('--hidden-dim', type=int, default=100,
                    help='hidden dimension size of encoder and decoder')
parser.add_argument('--learning-rate', type=int, default=-4,
                    help='exponent of the learning rate 10^(input) (default = -3)')
parser.add_argument('--latent-dim', type=int, default=100,
                    help='dimensions of latent space Z')
parser.add_argument('--epochs', type=int, default=20,
                    help='number of epochs to train (default: 20)')
parser.add_argument('--no-cuda', action='store_true', default=False,
                    help='enables CUDA training')
parser.add_argument('--seed', type=int, default=1,
                    help='random seed (default: 1)')
parser.add_argument('--randomize', action='store_true', default=False,
                    help='randomize pixel values according to Bernoulli(pixels) (default: False)')
parser.add_argument('--imp-samples', type=int, default=20)
parser.add_argument('--use-existing-model', action='store_true', default=False,
                    help='Use the model specified by the option model-path')
parser.add_argument('--model-path', type=str, default="saved_params/torch_new_bb_100_100_100_20_False_4",
                    help='path to existing model params (default: torch_new_bb_100_100_100_20_False_4)')

args = parser.parse_args()
args.cuda = not args.no_cuda and torch.cuda.is_available()

torch.cuda.manual_seed(args.seed)
device = torch.device("cuda" if args.cuda else "cpu")

kwargs = {'num_workers': 2, 'pin_memory': True} if args.cuda else {}
model_filename_suffix = "{}_{}_{}_{}_{}_{}".format(args.batch_size, args.hidden_dim, args.latent_dim, args.epochs, args.no_cuda, abs(args.learning_rate))
model_filename = "{}_{}".format(args.model_filename_prefix, model_filename_suffix)

class BinaryVAE(nn.Module):
    def __init__(self, data_size :int = 784, n_channels :int = 1, hidden_dim: int = 100, latent_dim: int = 40):
        super().__init__()
        
        self.hidden_dim = hidden_dim
        self.latent_dim = latent_dim
        self.data_size = data_size
        self.n_channels = n_channels

        self.layer11 = nn.Sequential(
            nn.Conv2d(1, 32, kernel_size = 3),
            nn.ReLU()
        )

        self.layer12 = nn.Sequential(
            nn.AvgPool2d(kernel_size = 2, stride = 2),
            nn.Conv2d(32, 64, kernel_size = 3),
            nn.ReLU()
        )

        self.layer13 = nn.Sequential(
            nn.AvgPool2d(kernel_size = 2, stride = 2),
            nn.Conv2d(64, 256, kernel_size = 5),
            nn.ReLU()
        )

        self.fc11 = nn.Linear(256, 100)
        self.fc12 = nn.Linear(256, 100)

        self.encoder = nn.Sequential(
            self.layer11,
            self.layer12,
            self.layer13,
        )

        self.fc21 = nn.Linear(100, 256)

        self.layer21 = nn.Sequential(
            nn.ReLU(),
            nn.Conv2d(256, 64, kernel_size = 5, padding = 4),
            nn.ReLU()
        )

        self.layer22 = nn.Sequential(
            nn.UpsamplingBilinear2d(scale_factor = 2),
            nn.Conv2d(64, 32, kernel_size = 3, padding = 2),
            nn.ReLU()
        )

        self.layer23 = nn.Sequential(
            nn.UpsamplingBilinear2d(scale_factor = 2),
            nn.Conv2d(32, 16, kernel_size = 3, padding = 2),
            nn.ReLU()
        )

        self.layer24 = nn.Conv2d(16, 1, kernel_size = 3, padding = 2)

        self.decoder = nn.Sequential(
            self.layer21,
            self.layer22,
            self.layer23,
            self.layer24
        )

        self.sigmoid = nn.Sigmoid()

    def encode(self, x):
        h0 = self.encoder(x).view(-1, x.data.shape[0], 256)
        mu, logvar = self.fc11(h0), self.fc12(h0)
        self.mu = mu
        self.logvar = logvar

        return mu, logvar

    def decode(self, z):
        h0 = self.fc21(z)
        decoded = self.decoder(h0.view(-1, h0.shape[-1], 1, 1))
        res = self.sigmoid(decoded)
        return res

    def reparameterize(self, mu, logvar):
        std = torch.exp(0.5*logvar)
        if self.training:
            eps = torch.randn_like(std)
            res = eps.mul(std).add_(mu)
        else:
            res = mu

        return res

    def forward(self, x):
        mu, logvar = self.encode(x)
        z = self.reparameterize(mu, logvar)
        x_ = self.decode(z)

        return x_, z, mu, logvar

    def BCEloss(self, inp, target):
        return (target.view(-1, 784)*torch.log(inp.view(-1, 784)) + (1 - target.view(-1, 784))*torch.log(1 - inp.view(-1, 784)))

    def loss(self, x):
        recon_x, z, mu, logvar = self.forward(x)
        dist = Bernoulli(recon_x.view(-1, 784))

        BCE = dist.log_prob(x.view(-1, 784)).sum()
        KLD = -0.5 * torch.sum(1 + logvar - mu.pow(2) -  torch.exp(logvar), dim = 1)

        negative_elbo = torch.sum(KLD) - BCE

        return negative_elbo, mu, logvar

    def sample(self, n = 64):
        z = torch.randn(n, self.latent_dim).to(device)
        x_recon = self.decode(z)
        return x_recon

def calc_normal_log_pdf(x, mean, variance):
    return -0.5 * torch.pow(x - mean, 2) * torch.reciprocal(variance) - 0.5 * torch.log(2 * math.pi * variance)

def marginal(model, x, z):

    k = z.shape[1]
    mu, logvar = model.encode(x)
    mu = mu.squeeze(0)
    logvar = logvar.squeeze(0)
    std = torch.exp(0.5*logvar)
    batchsize = x.data.shape[0]
    logsums = torch.empty((batchsize, 1)).to(device)
    
    z = z.view(k, batchsize, -1)
    q_z = Normal(mu, std)
    
    zero_mean = torch.zeros(batchsize, model.latent_dim).to(device)
    one_std = torch.ones(batchsize, model.latent_dim).to(device)
    p_z = Normal(torch.zeros(batchsize, model.latent_dim).to(device), torch.ones(batchsize, model.latent_dim).to(device))
    
    for i in range(k):
        zs = z[i]
        recon_xs = model.decode(zs)
        p_xz = Bernoulli(recon_xs.view(batchsize, 784))

        xs = x.view(batchsize, 784)
        log_pxs = torch.sum(p_xz.log_prob(xs), dim = 1)

        log_prior = calc_normal_log_pdf(zs, zero_mean, one_std).sum(dim = 1)
        log_posterior = calc_normal_log_pdf(zs, mu, std).sum(dim = 1)

        logsum = log_pxs + log_prior - log_posterior
        logsums = torch.cat((logsums, logsum[:,None]), dim = 1)

    logsums = logsums[:,1:]
    res = torch.logsumexp(logsums, dim = 1) - math.log(k)

    return res

def train(model, epoch, data_loader, optimizer, log_interval=10):
    model.train()
    train_loss = 0
    i = 0
    num_samples = 0
    for batch_idx, data in enumerate(data_loader):
        data = data.to(device)
        with autograd.detect_anomaly():
            optimizer.zero_grad()
            loss, _, _ = model.loss(data)
            train_loss += loss.item()
            loss /= data.shape[0]
            loss.backward()

        optimizer.step()
        i += 1
        num_samples += data.shape[0]
        if batch_idx % log_interval == 0:
            print('Train Epoch: {} [{}/{} ({:.0f}%)]\tELBO: {:.6f}'.format(
                epoch, batch_idx * len(data), len(data_loader.dataset),
                100. * batch_idx / len(data_loader),
                -loss.item()))

    print('Epoch: {} Average ELBO: {:.4f}'.format(
        epoch, -train_loss / num_samples))

def test(model, epoch, batch_size, num_imp_samples, data_loader):
    model.eval()
    test_loss = 0
    num_samples = 0
    marginals = 0 
    
    with torch.no_grad():
        for i, data in enumerate(data_loader):
            data = data.to(device)
            loss, mu, logvar = model.loss(data)
            test_loss += loss.item()
           
            batchsize = data.data.shape[0]
            q_z = Normal(mu, torch.exp(0.5 * logvar))
            zs = q_z.sample_n(num_imp_samples).view(batchsize, num_imp_samples, -1)
            
            ll_batch = marginal(model, data, zs) 
            marginals = marginals + torch.sum(ll_batch).item()
            print(f"Minibatch [{i}/{len(data_loader)}] elbo = {-loss.item()/batchsize}, Log Likelihood of minibatch  = {ll_batch.mean().item()}")
            num_samples += data.shape[0]
        
    print("\nELBO = {}, marginal probability = {}\n".format(-test_loss/num_samples, marginals / num_samples))


## The following data loader was provided by CW_Huang ""
def get_data_loader(dataset_location, batch_size):
    URL = "http://www.cs.toronto.edu/~larocheh/public/datasets/binarized_mnist/"
    # start processing
    def lines_to_np_array(lines):
        return np.array([[int(i) for i in line.split()] for line in lines])
    
    splitdata = []
    for splitname in ["train", "valid", "test"]:
        filename = "binarized_mnist_%s.amat" % splitname
        filepath = os.path.join(dataset_location, filename)
        utils.download_url(URL + filename, dataset_location)
        with open(filepath) as f:
            lines = f.readlines()
            x = lines_to_np_array(lines).astype('float32')
            x = x.reshape(x.shape[0], 1, 28, 28)
            # pytorch data loader
            dataset = data_utils.TensorDataset(torch.from_numpy(x))
            dataset_loader = data_utils.DataLoader(x, batch_size=batch_size, shuffle=splitname == "train")
            splitdata.append(dataset_loader)
    
    return splitdata


def run():
    
    model = BinaryVAE(784, 1, args.hidden_dim, args.latent_dim).to(device)

    optimizer = optim.Adam(model.parameters(), lr = 3*math.pow(10, args.learning_rate))
    train_loader, valid_loader, test_loader = get_data_loader("binarized_mnist", args.batch_size)

    try:
        if args.use_existing_model:
            print(f"Using existing model state dictionary from: {args.model_path}")
            model.load_state_dict(torch.load(args.model_path))
            test(model, 1, args.batch_size, args.imp_samples, valid_loader)
            test(model, 1, args.batch_size, args.imp_samples, test_loader)
        else:
            for epoch in range(1, args.epochs + 1):
                train(model, epoch, train_loader, optimizer)
            
            torch.save(model.state_dict(), 'saved_params/{}'.format(model_filename))
            test(model, epoch, args.batch_size, args.imp_samples, valid_loader)
            test(model, epoch, args.batch_size, args.imp_samples, test_loader)

    except KeyboardInterrupt:
        torch.save(model.state_dict(), 'saved_params/{}'.format(model_filename))

if __name__ == "__main__":
    run()
