import math

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.autograd import Variable

# Necessary for my KFAC implementation.
class AddBias(nn.Module):
    def __init__(self, bias):
        super(AddBias, self).__init__()
        self._bias = nn.Parameter(bias.unsqueeze(1))

    def forward(self, x):
        if x.dim() == 2:
            bias = self._bias.t().view(1, -1)
        else:
            bias = self._bias.t().view(1, -1, 1, 1)

        return x + bias

# Output single value
# Build prob based on this single value
class Categorical(nn.Module):
    def __init__(self, num_inputs, num_outputs):
        super(Categorical, self).__init__()
        self.linear = nn.Linear(num_inputs, num_outputs)

    def forward(self, x):
        x = self.linear(x)
        return x

    # why
    def sample(self, x, deterministic):
        # (20, 1024) -> (20, 6)
        x = self.forward(x)

        probs = F.softmax(x, dim=1)
        if deterministic is False:
            action = probs.multinomial(num_samples=1)
        else:
            action = probs.max(1, keepdim=True)[1]
        # print('kak {}'.format(action))
        return action

    def logprobs_and_entropy(self, x, actions):
        x = self.forward(x)

        log_probs = F.log_softmax(x, dim=1)
        probs = F.softmax(x, dim=1)

        action_log_probs = log_probs.gather(1, actions)

        dist_entropy = -(log_probs * probs).sum(-1).mean()
        return action_log_probs, dist_entropy


class DiagGaussian(nn.Module):
    def __init__(self, num_inputs, num_outputs):
        super(DiagGaussian, self).__init__()
        self.fc_mean = nn.Linear(num_inputs, num_outputs)
        self.logstd = AddBias(torch.zeros(num_outputs))

    def forward(self, x):
        action_mean = self.fc_mean(x)

        #  An ugly hack for my KFAC implementation.
        zeros = Variable(torch.zeros(action_mean.size()), volatile=x.volatile)
        if x.is_cuda:
            zeros = zeros.cuda()

        action_logstd = self.logstd(zeros)
        return action_mean, action_logstd

    def sample(self, x, deterministic):
        action_mean, action_logstd = self(x)

        action_std = action_logstd.exp()

        if deterministic is False:
            noise = Variable(torch.randn(action_std.size()))
            if action_std.is_cuda:
                noise = noise.cuda()
            action = action_mean + action_std * noise
        else:
            action = action_mean
        return action

    def logprobs_and_entropy(self, x, actions):
        action_mean, action_logstd = self(x)

        action_std = action_logstd.exp()

        action_log_probs = -0.5 * ((actions - action_mean) / action_std).pow(2) - 0.5 * math.log(2 * math.pi) - action_logstd
        action_log_probs = action_log_probs.sum(-1, keepdim=True)
        dist_entropy = 0.5 + 0.5 * math.log(2 * math.pi) + action_logstd
        dist_entropy = dist_entropy.sum(-1).mean()
        return action_log_probs, dist_entropy


def get_distribution(num_inputs, action_space):
    if action_space.__class__.__name__ == "Discrete":
        num_outputs = action_space.n
        dist = Categorical(num_inputs, num_outputs)
    # elif action_space.__class__.__name__ == "Box":
    #     num_outputs = action_space.shape[0]
    #     dist = DiagGaussian(num_inputs, num_outputs)
    else:
        raise NotImplementedError
    return dist
