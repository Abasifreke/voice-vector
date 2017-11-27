# -*- coding: utf-8 -*-
# !/usr/bin/env python

import tensorflow as tf
import os
from modules import conv1d_banks, conv1d, normalize, highwaynet, prenet


class Model:
    '''
    n = batch size
    t = timestep size
    h = hidden size
    e = embedding size
    '''

    def __init__(self, data_loader, num_banks, hidden_units, num_highway, norm_type, embedding_size, is_training):
        self.is_training = is_training
        self.num_banks = num_banks
        self.hidden_units = hidden_units
        self.num_highway = num_highway
        self.norm_type = norm_type
        self.embedding_size = embedding_size

        # Input
        self.x, self.x_pos, self.x_neg = data_loader.get_batch_queue()  # (n, t, 1 + n_fft/2)

        # Networks
        self.net = tf.make_template('net', self.embedding)
        self.y = self.net(self.x)  # (n, e)
        self.y_pos = self.net(self.x_pos)  # (n, e)
        self.y_neg = self.net(self.x_neg)  # (n, e)

    def __call__(self):
        return self.y

    def embedding(self, x):
        '''
        
        :param x: (n, t, 1 + n_fft/2)
        :return: (n, e)
        '''

        # Frame-level embedding
        x = tf.layers.dense(x, units=self.hidden_units, activation=tf.nn.relu)   # (n, t, h)

        out = conv1d_banks(x, K=self.num_banks, num_units=self.hidden_units, norm_type=self.norm_type,
                           is_training=self.is_training)  # (n, t, k * h)

        out = tf.layers.max_pooling1d(out, 2, 1, padding="same")  # (n, t, k * h)

        out = conv1d(out, self.hidden_units, 3, scope="conv1d_1")  # (n, t, h)
        out = normalize(out, type=self.norm_type, is_training=self.is_training, activation_fn=tf.nn.relu)
        out = conv1d(out, self.hidden_units, 3, scope="conv1d_2")  # (n, t, h)
        out += x  # (n, t, h) # residual connections

        for i in range(self.num_highway):
            out = highwaynet(out, num_units=self.hidden_units, scope='highwaynet_{}'.format(i))  # (n, t, h)

        out = tf.layers.dense(out, self.embedding_size)  # (n, t, e)

        # Average on frames
        out = tf.reduce_mean(out, axis=1)  # (n, e)

        return out

    def loss(self):
        # embed_x = self.embedding(self.x)
        # embed_x_pos = self.embedding(self.x_pos)
        # embed_x_neg = self.embedding(self.x_neg)
        # triplet_loss = tf.losses.cosine_distance(embed_x, embed_x_pos, dim=1) - tf.losses.cosine_distance(embed_x, embed_x_neg, dim=1)
        triplet_loss = tf.losses.cosine_distance(self.y, self.y_pos, dim=1) - tf.losses.cosine_distance(self.y, self.y_neg, dim=1)
        return triplet_loss  # (n, e)

    @staticmethod
    def load(sess, logdir):
        ckpt = tf.train.latest_checkpoint(logdir)
        if ckpt:
            tf.train.Saver().restore(sess, ckpt)
            model_name = Model.get_model_name(logdir)
            if model_name:
                print('Model loaded: {}'.format(model_name))
            else:
                print('Model created.')

    @staticmethod
    def get_model_name(logdir):
        path = '{}/checkpoint'.format(logdir)
        if os.path.exists(path):
            ckpt_path = open(path, 'r').read().split('"')[1]
            _, model_name = os.path.split(ckpt_path)
        else:
            model_name = None
        return model_name

    @staticmethod
    def get_global_step(logdir):
        model_name = Model.get_model_name(logdir)
        gs = 0
        if model_name:
            tokens = model_name.split('_')
            gs = int(tokens[1])
        return gs

    @staticmethod
    def all_model_names(logdir):
        import glob, os
        path = '{}/*.meta'.format(logdir)
        model_names = map(lambda f: os.path.basename(f).replace('.meta', ''), glob.glob(path))
        return model_names