#coding:utf8
from baseclass.DeepRecommender import DeepRecommender
from baseclass.SocialRecommender import SocialRecommender
from random import choice
import tensorflow as tf
from collections import defaultdict
import numpy as np
from math import sqrt


def gumbel_softmax(logits, temperature=0.2):
    eps = 1e-20
    u = tf.random_uniform(tf.shape(logits), minval=0, maxval=1)
    gumbel_noise = -tf.log(-tf.log(u + eps) + eps)
    y = tf.log(logits + eps) + gumbel_noise
    return tf.nn.softmax(y / temperature)


class AGR(SocialRecommender,DeepRecommender):

    def __init__(self,conf,trainingSet=None,testSet=None,relation=None,fold='[1]'):
        DeepRecommender.__init__(self, conf=conf, trainingSet=trainingSet, testSet=testSet, fold=fold)
        SocialRecommender.__init__(self, conf=conf, trainingSet=trainingSet, testSet=testSet, relation=relation,fold=fold)

    def next_batch(self):
        batch_id = 0
        while batch_id < self.train_size:
            if batch_id + self.batch_size <= self.train_size:
                users = [self.data.trainingData[idx][0] for idx in range(batch_id, self.batch_size + batch_id)]
                items = [self.data.trainingData[idx][1] for idx in range(batch_id, self.batch_size + batch_id)]
                batch_id += self.batch_size
            else:
                users = [self.data.trainingData[idx][0] for idx in range(batch_id, self.train_size)]
                items = [self.data.trainingData[idx][1] for idx in range(batch_id, self.train_size)]
                batch_id = self.train_size

            u_idx, i_idx, j_idx = [], [], []
            item_list = self.data.item.keys()
            for i, user in enumerate(users):

                i_idx.append(self.data.item[items[i]])
                u_idx.append(self.data.user[user])

                neg_item = choice(item_list)
                while neg_item in self.data.trainSet_u[user]:
                    neg_item = choice(item_list)
                j_idx.append(self.data.item[neg_item])

            yield u_idx, i_idx, j_idx

    def sampling(self,vec):

        vec = tf.nn.softmax(vec)

        logits = gumbel_softmax(vec, 0.1)
        return logits


    def buildGraph(self):

        self.weights = dict()
        initializer = tf.contrib.layers.xavier_initializer()
        #Generator
        self.g_params = []

        # self.CUNet = defaultdict(dict)
        # print 'Building the collaborative user net. It may take a few seconds...'
        # self.implictConnection = []

        self.isTraining = tf.placeholder(tf.int32)
        self.isTraining = tf.cast(self.isTraining, tf.bool)

        # for user1 in self.data.trainSet_u:
        #     s1 = set(self.data.trainSet_u[user1])
        #     for user2 in self.data.trainSet_u:
        #         if user1 <> user2:
        #             s2 = set(self.data.trainSet_u[user2])
        #             weight = len(s1.intersection(s2))
        #             if weight > 0:
        #                 self.CUNet[user1][user2] = weight
        #                 self.implictConnection.append((user1, user2, weight))

        indices = [[self.data.user[item[0]], self.num_users + self.data.item[item[1]]] for item in
                   self.data.trainingData]
        indices += [[self.num_users + self.data.item[item[1]], self.data.user[item[0]]] for item in
                    self.data.trainingData]
        values = [float(item[2]) / sqrt(len(self.data.trainSet_u[item[0]])) / sqrt(
            len(self.data.trainSet_i[item[1]])) for item in self.data.trainingData] * 2

        R = tf.SparseTensor(indices=indices, values=values,
                                   dense_shape=[self.num_users + self.num_items, self.num_users + self.num_items])


        with tf.name_scope("generator"):
            user_embeddings = tf.Variable(tf.truncated_normal(shape=[self.num_users, self.embed_size], stddev=0.005), name='g_U')
            item_embeddings = tf.Variable(tf.truncated_normal(shape=[self.num_items, self.embed_size], stddev=0.005), name='g_I')

            ego_embeddings = tf.concat([self.user_embeddings, self.item_embeddings], axis=0)

            self.g_params.append(user_embeddings)
            self.g_params.append(item_embeddings)

            indices+= [[self.data.user[item[0]], self.data.user[item[1]]] for item in
                self.social.relation]

            values += [float(item[2]) / sqrt(len(self.social.followees[item[0]])+1) / sqrt(
                len(self.social.followers[item[1]])+1) for item in self.social.relation]

            S_R = tf.SparseTensor(indices=indices, values=values,
                                   dense_shape=[self.num_users+self.num_items, self.num_users+self.num_items])


            weight_size = [self.embed_size, self.embed_size, self.embed_size]
            weight_size_list = [self.embed_size] + weight_size

            social_graph_layers = 3

            # initialize parameters
            for k in range(social_graph_layers):
                self.weights['g_W_%d_1' % k] = tf.Variable(
                    initializer([weight_size_list[k], weight_size_list[k + 1]]), name='g_W_%d_1' % k)
                self.weights['g_W_%d_2' % k] = tf.Variable(
                    initializer([weight_size_list[k], weight_size_list[k + 1]]), name='g_W_%d_2' % k)
                self.g_params.append(self.weights['g_W_%d_1' % k])
                self.g_params.append(self.weights['g_W_%d_2' % k])

            all_g_embeddings = [ego_embeddings]
            for k in range(social_graph_layers):
                side_embeddings = tf.sparse_tensor_dense_matmul(S_R, ego_embeddings)
                sum_embeddings = tf.matmul(side_embeddings + ego_embeddings, self.weights['g_W_%d_1' % k])
                bi_embeddings = tf.multiply(ego_embeddings, side_embeddings)
                bi_embeddings = tf.matmul(bi_embeddings, self.weights['g_W_%d_2' % k])

                ego_embeddings = tf.nn.leaky_relu(sum_embeddings + bi_embeddings)

                # message dropout.
                def without_dropout():
                    return ego_embeddings

                def dropout():
                    return tf.nn.dropout(ego_embeddings, keep_prob=0.9)

                ego_embeddings = tf.cond(self.isTraining, lambda: dropout(), lambda: without_dropout())

                # normalize the distribution of embeddings.
                norm_embeddings = tf.math.l2_normalize(ego_embeddings, axis=1)

                all_g_embeddings += [norm_embeddings]


            g_total_embeddings = sum(all_g_embeddings)/social_graph_layers

            g_user_embeddings, g_item_embeddings = tf.split(g_total_embeddings,[self.num_users, self.num_items], 0)


            self.g_u_embedding = tf.nn.embedding_lookup(g_user_embeddings, self.u_idx)
            self.g_i_embedding = tf.nn.embedding_lookup(g_item_embeddings, self.v_idx)
        #MLP (friend and item generation)
        with tf.name_scope("item_generator"):

            u_features = self.g_u_embedding + self.g_i_embedding + tf.multiply(self.g_u_embedding,self.g_i_embedding)

            u_scores = tf.matmul(u_features,g_user_embeddings,transpose_b=True)

            #one_hot implicit friend
            self.implicit_friend = self.sampling(u_scores)
            indices = [[self.data.item[item[1]], self.data.user[item[0]]] for item in self.data.trainingData]
            values = [item[2] for item in self.data.trainingData]
            self.i_u_matrix = tf.SparseTensor(indices=indices, values=values,
                                              dense_shape=[self.num_items, self.num_users])

            self.item_selection = tf.get_variable('item_selection', initializer=tf.constant_initializer(0.01),
                                                  shape=[self.num_users, self.num_items])
            self.g_params.append(self.item_selection)

            # get candidate list (items)
            self.candidateItems = tf.transpose(
                tf.sparse_tensor_dense_matmul(self.i_u_matrix, tf.transpose(self.implicit_friend)))

            # f_features = tf.matmul(self.implicit_friend,g_user_embeddings)
            # f_features += self.g_i_embedding + tf.multiply(f_features,self.g_i_embedding)
            # i_scores = tf.matmul(f_features,g_item_embeddings,transpose_b=True)

            embedding_selection = tf.nn.embedding_lookup(self.item_selection, self.u_idx, name='e_s')

            self.virtual_items = self.sampling(tf.multiply(self.candidateItems, embedding_selection))


        self.d_weights = dict()
        #Discriminator
        self.d_params = [self.user_embeddings, self.item_embeddings]
        with tf.name_scope("discrminator"):
            ego_embeddings = tf.concat([self.user_embeddings, self.item_embeddings], axis=0)

            weight_size = [self.embed_size, self.embed_size, self.embed_size]
            weight_size_list = [self.embed_size] + weight_size

            self.n_layers = 3

            # initialize parameters
            for k in range(self.n_layers):
                self.weights['W_%d_1' % k] = tf.Variable(
                    initializer([weight_size_list[k], weight_size_list[k + 1]]), name='W_%d_1' % k)
                self.weights['W_%d_2' % k] = tf.Variable(
                    initializer([weight_size_list[k], weight_size_list[k + 1]]), name='W_%d_2' % k)
                self.d_params.append(self.weights['W_%d_1' % k])
                self.d_params.append(self.weights['W_%d_2' % k])

            all_embeddings = [ego_embeddings]
            for k in range(self.n_layers):
                side_embeddings = tf.sparse_tensor_dense_matmul(R, ego_embeddings)
                #friend_embeddings = tf.matmul(self.implicit_friend, ego_embeddings[:self.num_users])

                sum_embeddings = tf.matmul(side_embeddings + ego_embeddings, self.weights['W_%d_1' % k])
                bi_embeddings = tf.multiply(ego_embeddings, side_embeddings)
                bi_embeddings = tf.matmul(bi_embeddings, self.weights['W_%d_2' % k])

                ego_embeddings = tf.nn.leaky_relu(sum_embeddings + bi_embeddings)

                # message dropout.
                def without_dropout():
                    return ego_embeddings

                def dropout():
                    return tf.nn.dropout(ego_embeddings, keep_prob=0.9)

                ego_embeddings = tf.cond(self.isTraining, lambda: dropout(), lambda: without_dropout())

                # normalize the distribution of embeddings.
                norm_embeddings = tf.math.l2_normalize(ego_embeddings, axis=1)

                all_embeddings += [norm_embeddings]

            total_embeddings = tf.concat(all_embeddings, 1)

            self.multi_user_embeddings, self.multi_item_embeddings = tf.split(total_embeddings,
                                                                              [self.num_users, self.num_items], 0)


            self.neg_idx = tf.placeholder(tf.int32, name="neg_holder")
            self.neg_item_embedding = tf.nn.embedding_lookup(self.multi_item_embeddings, self.neg_idx)
            self.u_embedding = tf.nn.embedding_lookup(self.multi_user_embeddings, self.u_idx)
            self.v_embedding = tf.nn.embedding_lookup(self.multi_item_embeddings, self.v_idx)
            self.v_i_embedding = tf.matmul(self.virtual_items, self.multi_item_embeddings, transpose_a=False,
                                           transpose_b=False)

    def initModel(self):
        super(AGR, self).initModel()
        self.buildGraph()

    def buildModel(self):

        y_uf = tf.reduce_sum(tf.multiply(self.u_embedding, self.v_embedding), 1) - \
               tf.reduce_sum(tf.multiply(self.u_embedding, self.v_i_embedding), 1)

        y_fs = tf.reduce_sum(tf.multiply(self.u_embedding, self.v_i_embedding), 1) - \
               tf.reduce_sum(tf.multiply(self.u_embedding, self.neg_item_embedding), 1)

        self.d_loss = -tf.reduce_sum(tf.log(tf.sigmoid(y_uf))) - tf.reduce_sum(tf.log(tf.sigmoid(y_fs))) + \
                      self.regU * (tf.nn.l2_loss(self.u_embedding) + tf.nn.l2_loss(self.v_embedding) + tf.nn.l2_loss(
            self.neg_item_embedding))
        #
        self.g_loss = 30 * tf.reduce_sum(y_uf)  # better performance


        self.d_output = tf.reduce_sum(tf.multiply(self.u_embedding, self.multi_item_embeddings), 1)

        d_opt = tf.train.AdamOptimizer(self.lRate)

        self.d_update = d_opt.minimize(self.d_loss, var_list=self.d_params)

        g_opt = tf.train.AdamOptimizer(self.lRate)
        self.g_update = g_opt.minimize(self.g_loss, var_list=self.g_params)

        init = tf.global_variables_initializer()
        self.sess.run(init)
        print 'Training GAN...'

        for i in range(self.maxIter):

            for num, batch in enumerate(self.next_batch()):
                user_idx, i_idx, j_idx = batch

                # generator
                _, loss = self.sess.run([self.g_update, self.g_loss],
                                        feed_dict={self.u_idx: user_idx, self.neg_idx: j_idx,
                                                   self.v_idx: i_idx,self.isTraining:1})

                # discriminator
                _, loss = self.sess.run([self.d_update, self.d_loss],
                                        feed_dict={self.u_idx: user_idx, self.neg_idx: j_idx,
                                                   self.v_idx: i_idx,self.isTraining:1})

                print 'training:', i + 1, 'batch_id', num, 'discriminator loss:', loss

    def predictForRanking(self, u):
        'invoked to rank all the items for the user'
        if self.data.containsUser(u):
            u = self.data.user[u]

            # In our experiments, discriminator performs better than generator
            res = self.sess.run(self.d_output, {self.u_idx:u,self.isTraining:0})
            return res

        else:
            return [self.data.globalMean] * self.num_items