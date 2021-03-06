#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Author: Linjian Zhang
Email: linjian93@foxmail.com
Creat Time: 2017-10-02 14:27:57
Program: 
Description: 
"""
import tensorflow as tf
import tensorflow.contrib.slim as slim
import pickle
import numpy as np

flags = tf.app.flags
flags.DEFINE_integer('batch_size', 256, 'batch size')
flags.DEFINE_integer('img_dim', 1024, 'image feature vector dimension')
flags.DEFINE_integer('embed_dim', 512, 'word embed dimension')
flags.DEFINE_integer('hidden_dim', 512, 'lstm hidden dimension')
flags.DEFINE_integer('num_layer', 3, 'number of lstm layers')
flags.DEFINE_bool('use_gpu_1', False, 'whether to use gpu 1')
FLAGS = flags.FLAGS

dir_restore = 'model/image_caption/20171003_2/model-100'


class Net(object):
    def __init__(self, use_gpu_1=False, index2token=None):
        self.x1 = tf.placeholder(tf.int32, [None, None], name='x1')  # sentence 15 [SOS, w1, w2, ..., w13, EOS]
        self.x2 = tf.placeholder(tf.float32, [None, FLAGS.img_dim], name='x2')  # image [bs, 1024]
        self.lr = tf.placeholder(tf.float32, [], name='lr')  # lr
        self.kp = tf.placeholder(tf.float32, [], name='kp')  # keep_prob
        self.index2token = index2token
        self.vocab_size = len(index2token)

        with tf.variable_scope('image_fc'):
            fc1 = slim.fully_connected(self.x2, FLAGS.embed_dim, activation_fn=tf.nn.sigmoid, scope='fc1')
            img_input = tf.expand_dims(fc1, 1)  # [bs, 1, 512]
        with tf.variable_scope('sentence_embedding'):
            word_embeddings = tf.get_variable('word_embeddings', shape=[self.vocab_size, FLAGS.embed_dim])
            sent_inputs = tf.nn.embedding_lookup(word_embeddings, self.x1)  # [bs, 15, 512]
            lstm_inputs = tf.concat(1, [img_input, sent_inputs])  # [bs, 16, 512]-->16 [img, SOS, w1, w2, ..., w13, EOS]
        with tf.variable_scope('lstm'):
            cell = tf.nn.rnn_cell.BasicLSTMCell(FLAGS.hidden_dim)
            cell = tf.nn.rnn_cell.DropoutWrapper(cell, input_keep_prob=self.kp, output_keep_prob=self.kp)
            cell = tf.nn.rnn_cell.MultiRNNCell([cell] * FLAGS.num_layer)
            # initial_state = cell.zero_state(FLAGS.batch_size, tf.float32)
            output, _ = tf.nn.dynamic_rnn(cell, lstm_inputs, dtype=tf.float32)  # [bs, 16, 512]-->16 [x, w1, w2, ..., w13, EOS, x]
            output = tf.reshape(output, [-1, FLAGS.hidden_dim])  # [bs*ts, 512]
        with tf.variable_scope('softmax'):
            self.logits = slim.fully_connected(output, self.vocab_size, activation_fn=None, scope='softmax')  # [bs*ts, vs]

        self.predictions = tf.reshape(tf.argmax(self.logits, 1), [FLAGS.batch_size, -1])  # [bs, 16] --> for test
        self.t_vars = tf.trainable_variables()

        # logits for loss
        logits_reshape = tf.reshape(self.logits, [FLAGS.batch_size, -1, self.vocab_size])  # [bs, 16, vs]
        logits_final = logits_reshape[:, 1: -1, :]  # [bs, 14, vs]-->[w1, w2, ..., w13, EOS]
        self.logits_for_loss = tf.reshape(logits_final, [-1, self.vocab_size])  # [bs*14, vs]

        # loss
        target = self.x1[:, 1:]  # remove SOS
        target_reshaped = tf.reshape(target, [-1])  # [bs*14, ]
        self.loss = tf.reduce_mean(tf.nn.sparse_softmax_cross_entropy_with_logits(logits=self.logits_for_loss, labels=target_reshaped))
        optimizer = tf.train.AdamOptimizer(self.lr)
        self.train_op = optimizer.minimize(self.loss)

        # tensor board
        loss_summary = tf.summary.scalar('loss', self.loss)
        self.summary_merge = tf.summary.merge([loss_summary])

        # gpu configuration
        self.tf_config = tf.ConfigProto()
        self.tf_config.gpu_options.allow_growth = True
        if use_gpu_1:
            self.tf_config.gpu_options.visible_device_list = '1'

        # last but no least, get all the variables
        self.init_all = tf.initialize_all_variables()

    def generate_caption(self, sess, img_feature):
        # <SOS>: 3591
        # <EOS>: 3339
        img_template = np.zeros([FLAGS.batch_size, FLAGS.img_dim])
        img_template[0, :] = img_feature
        sent_input = np.ones([FLAGS.batch_size, 1]) * 3591  # <SOS>  # [bs, 1]->
        while sent_input[0, -1] != 3339 and (sent_input.shape[1] - 1) < 50:
            feed_dicts_t = {self.x1: sent_input, self.x2: img_template, self.kp: 1}
            predicted_total = sess.run(self.predictions, feed_dicts_t)  # [bs, 2]->[bs, 3]
            predicted_next = predicted_total[:, -1:]  # [bs, 1]
            sent_input = np.concatenate([sent_input, predicted_next], 1)  # [bs, 2]
        predicted_sentence = ' '.join(self.index2token[idx] for idx in sent_input[0, 1: -1])
        return predicted_sentence


def test_train_set():
    with open('data/mscoco/index2token.pkl', 'r') as f:
        index2token = pickle.load(f)

    with open('data/mscoco/train_82783.pkl', 'r') as f:
        train_image_id2feature = pickle.load(f)
    ks = [k for k, _ in sorted(train_image_id2feature.items(), key=lambda item: item[0])]
    vs = [v for _, v in sorted(train_image_id2feature.items(), key=lambda item: item[0])]
    img_vector = vs[12]
    img_id = ks[12]
    print 'image id: ', img_id
    with open('data/mscoco/preprocessed_train_captions.pkl', 'r') as f:
        _, caption_id2sentence, caption_id2image_id = pickle.load(f)

    caption_ids = [k for k, v in caption_id2image_id.items() if v == img_id]
    captions = [caption_id2sentence[caption_id] for caption_id in caption_ids]
    print 'gt captions: '
    for sentence_id in captions:
        sentence = ' '.join(index2token[idx] for idx in sentence_id[1: -1])
        print sentence

    # with open('data/image-features-test/pizza.pkl', 'r') as f:
    #     img_vector = pickle.load(f)
    print 'vocab size: ', len(index2token)
    model = Net(use_gpu_1=FLAGS.use_gpu_1, index2token=index2token)

    saver = tf.train.Saver()
    with tf.Session(config=model.tf_config) as sess:
        saver.restore(sess, dir_restore)
        caption = model.generate_caption(sess, img_vector)
        print 'predicted caption: '
        print caption


def test_val_set():
    with open('data/mscoco/index2token.pkl', 'r') as f:
        index2token = pickle.load(f)

    with open('data/mscoco/val_40504.pkl', 'r') as f:
        train_image_id2feature = pickle.load(f)
    ks = [k for k, _ in sorted(train_image_id2feature.items(), key=lambda item: item[0])]
    vs = [v for _, v in sorted(train_image_id2feature.items(), key=lambda item: item[0])]
    img_vector = vs[20]
    img_id = ks[20]
    print 'image id: ', img_id

    print 'vocab size: ', len(index2token)
    model = Net(use_gpu_1=FLAGS.use_gpu_1, index2token=index2token)

    saver = tf.train.Saver()
    with tf.Session(config=model.tf_config) as sess:
        saver.restore(sess, dir_restore)
        caption = model.generate_caption(sess, img_vector)
        print 'predicted caption: '
        print caption


if __name__ == "__main__":
    test_val_set()
