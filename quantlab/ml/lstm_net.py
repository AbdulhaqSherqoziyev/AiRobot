"""The LSTM network, at module level so a saved model can be loaded by a worker."""

from torch import nn


class LstmNet(nn.Module):
    def __init__(self, n_features: int, hidden: int):
        super().__init__()
        self.lstm = nn.LSTM(n_features, hidden, batch_first=True)
        self.out = nn.Linear(hidden, 1)

    def forward(self, x):
        return self.out(self.lstm(x)[0][:, -1]).squeeze(-1)
