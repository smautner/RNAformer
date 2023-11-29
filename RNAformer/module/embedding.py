import math
import torch
import torch.nn as nn
import torch.nn.functional as F


class PosEmbedding(nn.Module):
    def __init__(self, vocab, model_dim, max_len, rel_pos_enc, initializer_range):

        super().__init__()

        self.rel_pos_enc = rel_pos_enc
        self.max_len = max_len

        self.embed_seq = nn.Embedding(vocab, model_dim)

        self.scale = nn.Parameter(torch.sqrt(torch.FloatTensor([model_dim // 2])), requires_grad=False)

        if rel_pos_enc:
            self.embed_pair_pos = nn.Linear(max_len, model_dim, bias=False)
        else:
            self.embed_pair_pos = nn.Linear(model_dim, model_dim, bias=False)

            pe = torch.zeros(max_len, model_dim)
            position = torch.arange(0, max_len).unsqueeze(1).type(torch.FloatTensor)
            div_term = torch.exp(
                torch.arange(0, model_dim, 2).type(torch.FloatTensor) * -(math.log(10000.0) / model_dim))
            pe[:, 0::2] = torch.sin(position * div_term)
            pe[:, 1::2] = torch.cos(position * div_term)
            pe = pe.unsqueeze(0)
            pe = torch.nn.Parameter(pe, requires_grad=False)
            self.register_buffer('pe', pe)

        self.initialize(initializer_range)  #

    def initialize(self, initializer_range):

        nn.init.normal_(self.embed_seq.weight, mean=0.0, std=initializer_range)
        nn.init.normal_(self.embed_pair_pos.weight, mean=0.0, std=initializer_range)

    def relative_position_encoding(self, src_seq):

        residue_index = torch.arange(src_seq.size()[1], device=src_seq.device).expand(src_seq.size())
        rel_pos = F.one_hot(torch.clip(residue_index, min=0, max=self.max_len - 1), self.max_len)

        if isinstance(self.embed_pair_pos.weight, torch.cuda.BFloat16Tensor):
            rel_pos = rel_pos.type(torch.bfloat16)
        elif isinstance(self.embed_pair_pos.weight, torch.cuda.HalfTensor):
            rel_pos = rel_pos.half()
        else:
            rel_pos = rel_pos.type(torch.float32)

        pos_encoding = self.embed_pair_pos(rel_pos)
        return pos_encoding

    def forward(self, src_seq):

        seq_embed = self.embed_seq(src_seq) * self.scale

        if self.rel_pos_enc:
            seq_embed = seq_embed + self.relative_position_encoding(src_seq)
        else:
            seq_embed = seq_embed + self.embed_pair_pos(self.pe[:, :src_seq.size(1)])

        return seq_embed

import ubergauss.tools as ut
class EmbedSequence2Matrix(nn.Module):
    def __init__(self, config):
        super().__init__()
        self.src_embed_1 = PosEmbedding(config.seq_vocab_size, config.model_dim, config.max_len,
                                        config.rel_pos_enc, config.initializer_range)
        self.src_embed_2 = PosEmbedding(config.seq_vocab_size, config.model_dim, config.max_len,
                                        config.rel_pos_enc, config.initializer_range)

        self.norm = nn.LayerNorm(config.model_dim)

    def forward(self, src_seq, p1,p2):
        seq_1_embed = self.src_embed_1(src_seq)
        seq_2_embed = self.src_embed_2(src_seq)


        pair_latent = seq_1_embed.unsqueeze(1) + seq_2_embed.unsqueeze(2)
        # ut.dumpfile((pair_latent,seq_1_embed,seq_2_embed, src_seq),'delme.del')
        # exit()

        pair_latent = self.norm(pair_latent)

        # hacking in our structure
        for i in [0,1]:
            pair_latent[i,:,:,0] = 0
            pair_latent[i,p1,p2,0] = 1
        return pair_latent
