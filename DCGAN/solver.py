import torch
import torch.nn.functional as func
import torchvision
import os
from torch import optim
from torch.autograd import Variable
from DCGAN.model import Discriminator
from DCGAN.model import Generator
from progress_bar import progress_bar


class DCGANSolver(object):
    def __init__(self, config, data_loader):
        self.generator = None
        self.discriminator = None
        self.g_optimizer = None
        self.d_optimizer = None
        self.z_dim = config.z_dim
        self.beta1 = config.beta1
        self.beta2 = config.beta2
        self.g_conv_dim = config.g_conv_dim
        self.d_conv_dim = config.d_conv_dim
        self.image_size = config.image_size
        self.data_loader = data_loader
        self.num_epochs = config.num_epochs
        self.batch_size = config.batch_size
        self.sample_size = config.sample_size
        self.lr = config.lr
        self.log_step = config.log_step
        self.sample_step = config.sample_step
        self.sample_path = config.sample_path
        self.model_path = config.model_path
        self.build_model()

    def build_model(self):
        """Build generator and discriminator."""
        self.generator = Generator(z_dim=self.z_dim, image_size=self.image_size, conv_dim=self.g_conv_dim)
        self.discriminator = Discriminator(image_size=self.image_size, conv_dim=self.d_conv_dim)
        # self.generator.weight_init(mean=0.0, std=0.02)
        # self.discriminator.weight_init(mean=0.0, std=0.02)
        self.g_optimizer = optim.Adam(self.generator.parameters(), self.lr, [self.beta1, self.beta2])
        self.d_optimizer = optim.Adam(self.discriminator.parameters(), self.lr, [self.beta1, self.beta2])

        if torch.cuda.is_available():
            self.generator.cuda()
            self.discriminator.cuda()

    @staticmethod
    def to_variable(x):
        """Convert tensor to variable."""
        if torch.cuda.is_available():
            x = x.cuda()
        return Variable(x)

    @staticmethod
    def to_data(x):
        """Convert variable to tensor."""
        if torch.cuda.is_available():
            x = x.cpu()
        return x.data

    def reset_grad(self):
        """Zero the gradient buffers."""
        self.discriminator.zero_grad()
        self.generator.zero_grad()

    @staticmethod
    def de_normalize(x):
        """Convert range (-1, 1) to (0, 1)"""
        out = (x + 1) / 2
        return out.clamp(0, 1)

    def fixed_noise(self):
        return self.to_variable(torch.randn(self.batch_size, self.z_dim))

    def save_model(self, epoch):
        g_path = os.path.join(self.model_path, 'DCGAN-generator-%d.pkl' % (epoch + 1))
        d_path = os.path.join(self.model_path, 'DCGAN-discriminator-%d.pkl' % (epoch + 1))
        torch.save(self.generator.state_dict(), g_path)
        torch.save(self.discriminator.state_dict(), d_path)

    def save_fakes(self, step, epoch):
        if (step + 1) % self.sample_step == 0:
            fake_images = self.generator(self.fixed_noise().view(-1, 100, 1, 1))
            torchvision.utils.save_image(self.de_normalize(fake_images.data),
                                         os.path.join(self.sample_path, 'DCGAN-fake_samples-%d-%d.png' % (epoch + 1, step + 1)))

    def train(self):
        """Train generator and discriminator."""

        total_step = len(self.data_loader)
        for epoch in range(self.num_epochs):
            print("===> Epoch [%d/%d]" % (epoch + 1, self.num_epochs))
            for i, images in enumerate(self.data_loader):

                # ===================== Train D ===================== #
                images = self.to_variable(images)
                noise = self.to_variable(torch.randn(images.size(0), self.z_dim))

                # Train D to recognize real images as real.
                outputs = self.discriminator(images)
                real_loss = func.binary_cross_entropy(outputs, Variable(torch.ones(images.size(0)).cuda()))

                # Train D to recognize fake images as fake.
                fake_images = self.generator(noise.view(-1, 100, 1, 1))
                outputs = self.discriminator(fake_images)
                fake_loss = func.binary_cross_entropy(outputs, Variable(torch.zeros(images.size(0)).cuda()))

                # Backpropagation + optimize
                self.reset_grad()
                d_loss = real_loss + fake_loss
                d_loss.backward()
                self.d_optimizer.step()

                # ===================== Train G =====================#
                noise = self.to_variable(torch.randn(images.size(0), self.z_dim))

                # Train G so that D recognizes G(z) as real.
                fake_images = self.generator(noise.view(-1, 100, 1, 1))
                outputs = self.discriminator(fake_images)
                g_loss = func.binary_cross_entropy(outputs, Variable(torch.ones(images.size(0)).cuda()))

                # Backpropagation + optimize
                self.reset_grad()
                g_loss.backward()
                self.g_optimizer.step()

                # print the log info via progress bar
                progress_bar(i, total_step, 'd_real_loss: %.4f | d_fake_loss: %.4f | g_loss: %.4f' % (real_loss.data[0], fake_loss.data[0], g_loss.data[0]))

                # save the sampled images
                self.save_fakes(step=i, epoch=epoch)

            # save the model parameters for each epoch
            self.save_model(epoch=epoch)

    def sample(self):
        # Load trained parameters
        g_path = os.path.join(self.model_path, 'generator-%d.pkl' % self.num_epochs)
        d_path = os.path.join(self.model_path, 'discriminator-%d.pkl' % self.num_epochs)
        self.generator.load_state_dict(torch.load(g_path))
        self.discriminator.load_state_dict(torch.load(d_path))
        self.generator.eval()
        self.discriminator.eval()

        # Sample the images
        noise = self.to_variable(torch.randn(self.sample_size, self.z_dim))
        fake_images = self.generator(noise)
        sample_path = os.path.join(self.sample_path, 'fake_samples-final.png')
        torchvision.utils.save_image(self.de_normalize(fake_images.data), sample_path, nrow=12)
        print("Saved sampled images to '%s'" % sample_path)