# Based on https://kratzert.github.io/2017/02/24/finetuning-alexnet-with-tensorflow.html

import tensorflow as tf
import numpy as np


def conv(x, filter_height, filter_width, num_filters, stride_y, stride_x, name,
         padding='SAME', groups=1, verbose_shapes=False, batch_norm=False):
    """Convolution function that can be split in multiple GPUs"""
    # Get number of input chennels
    input_channels = int(x.get_shape()[-1])

    if verbose_shapes:
        print('INPUT_CHANNELS', input_channels)
        print('X SHAPE conv', x.get_shape())

    convolve = lambda i, k: tf.nn.conv2d(i, k, strides=[1, stride_y, stride_x, 1],
                                         padding=padding)

    with tf.variable_scope(name) as scope:
        try:
            weights = tf.get_variable('weights',
                                      shape=[filter_height, filter_width, input_channels / groups, num_filters],
                                      trainable=True,
                                      initializer=tf.contrib.layers.xavier_initializer())
        except:
            tf.get_variable_scope().reuse_variables()
            weights = tf.get_variable('weights',
                                      shape=[filter_height, filter_width, input_channels / groups, num_filters],
                                      trainable=True,
                                      initializer=tf.contrib.layers.xavier_initializer())

        try:
            biases = tf.get_variable('biases', shape=[num_filters], trainable=True,
                                     initializer=tf.contrib.layers.xavier_initializer())
        except:
            tf.get_variable_scope().reuse_variables()
            biases = tf.get_variable('biases', shape=[num_filters], trainable=True,
                                     initializer=tf.contrib.layers.xavier_initializer())

        if groups == 1:
            conv = convolve(x, weights)
        else:
            input_groups = tf.split(axis=3, num_or_size_splits=groups, value=x)
            weight_groups = tf.split(axis=3, num_or_size_splits=groups, value=weights)
            output_groups = [convolve(i, k) for i, k in zip(input_groups, weight_groups)]

            conv = tf.concat(axis=3, values=output_groups)

        bias = tf.reshape(tf.nn.bias_add(conv, biases), conv.get_shape().as_list())
        if batch_norm:
            norm = lrn(bias, 2, 2e-05, 0.75, name=scope.name)
            relu = tf.nn.relu(norm, name=scope.name)
        else:
            relu = tf.nn.relu(bias, name=scope.name)

        return relu


def fc(x, num_in, num_out, name, relu=True, use_biases=True):
    """Full connected layer"""
    with tf.variable_scope(name) as scope:
        try:
            weights = tf.get_variable('weights', shape=[num_in, num_out], trainable=True,
                                      initializer=tf.contrib.layers.xavier_initializer())
        except:
            tf.get_variable_scope().reuse_variables()
            weights = tf.get_variable('weights', shape=[num_in, num_out], trainable=True,
                                      initializer=tf.contrib.layers.xavier_initializer())

        if use_biases:
            try:
                biases = tf.get_variable('biases', [num_out], trainable=True,
                                         initializer=tf.contrib.layers.xavier_initializer())
            except:
                tf.get_variable_scope().reuse_variables()
                biases = tf.get_variable('biases', [num_out], trainable=True,
                                         initializer=tf.contrib.layers.xavier_initializer())

            act = tf.nn.xw_plus_b(x, weights, biases, name=scope.name)
        else:
            act = tf.matmul(x, weights)

        if relu == True:
            relu = tf.nn.relu(act)
            return relu
        else:
            return act


def max_pool(x, filter_height, filter_width, stride_y, stride_x,
             name, padding='SAME', verbose_shapes=False):
    """Max pool layer"""
    if verbose_shapes:
        print('X SHAPE maxpool', x.get_shape())

    return tf.nn.max_pool(x, ksize=[1, filter_height, filter_width, 1],
                          strides=[1, stride_y, stride_x, 1],
                          padding=padding, name=name)


def lrn(x, radius, alpha, beta, name, bias=1.0, verbose_shapes=False):
    """Batch normalization"""
    if verbose_shapes:
        print('X SHAPE lrn', x.get_shape())

    return tf.nn.local_response_normalization(x, depth_radius=radius,
                                              alpha=alpha, beta=beta,
                                              bias=bias, name=name)


def avg_pool(x, filter_height, filter_width, stride_y, stride_x,
             name, padding='SAME', verbose_shapes=False):
    """Average pooling layer"""
    if verbose_shapes:
        print('X SHAPE avgpool', x.get_shape())

    return tf.nn.avg_pool(x, ksize=[1, filter_height, filter_width, 1],
                          strides=[1, stride_y, stride_x, 1],
                          padding=padding, name=name)


def normalize_images(x):
    """Normalize images before feeding into a CNN"""
    return tf.map_fn(lambda frame: tf.image.per_image_standardization(frame), x)


def dropout(x, keep_prob):
    """Dropout layer"""
    return tf.nn.dropout(x, keep_prob)


class AlexNet(object):
    """AlexNet model"""
    def __init__(self, x, num_classes):
        self.X = x
        self.NUM_CLASSES = num_classes
        self.create()

    def create(self):
        # 1st Layer: Conv (w ReLu) -> Lrn -> Pool
        normalized_images = normalize_images(self.X)
        self.conv1 = conv(normalized_images, 5, 5, 64, 1, 1, padding='VALID', name='conv1')
        norm1 = lrn(self.conv1, 2, 2e-05, 0.75, name='norm1')
        pool1 = max_pool(norm1, 3, 3, 2, 2, padding='VALID', name='pool1')

        # 2nd Layer: Conv (w ReLu) -> Lrn -> Poolwith 2 groups
        self.conv2 = conv(pool1, 5, 5, 64, 1, 1, groups=2, name='conv2')
        norm2 = lrn(self.conv2, 2, 2e-05, 0.75, name='norm2')
        pool2 = max_pool(norm2, 3, 3, 2, 2, padding='VALID', name='pool2')

        # 3th Layer: Flatten -> FC (w ReLu) -> Dropout
        self.flattened = tf.reshape(pool2, [-1, 4 * 4 * 64])
        self.fc3 = fc(self.flattened, 4 * 4 * 64, 384, name='fc3')

        # 4th Layer: FC (w ReLu) -> Dropout
        self.fc4 = fc(self.fc3, 384, 192, name='fc4')

        # 5th Layer: FC and return unscaled activations
        # (for tf.nn.softmax_cross_entropy_with_logits)
        self.fc5 = fc(self.fc4, 192, self.NUM_CLASSES, relu=False, name='fc5')


class Composite_model(object):
    """Visual-semantic embedding"""
    def __init__(self, x, num_classes, word2vec_size, use_vgg=False):
        self.X = x
        self.NUM_CLASSES = num_classes
        self.WORD2VEC_SIZE = word2vec_size
        self.use_vgg = use_vgg
        if self.use_vgg:
            self.image_repr_model = VGG19(self.X, 0.5, self.NUM_CLASSES)
        else:
            self.image_repr_model = AlexNet(self.X, self.NUM_CLASSES)
        self.create()

    def create(self):
        if self.use_vgg:
            self.image_repr = self.image_repr_model.fc7
            self.projection_layer = fc(self.image_repr, 4096, self.WORD2VEC_SIZE, name='proj', relu=False,
                                       use_biases=True)
        else:
            self.image_repr = self.image_repr_model.fc4
            self.projection_layer = fc(self.image_repr, 192, self.WORD2VEC_SIZE, name='proj', relu=False,
                                       use_biases=True)


class Reverse_model(object):
    def __init__(self, x, word2vec_size, image_size):
        self.X = x
        self.WORD2VEC_SIZE = word2vec_size
        self.IMAGE_SIZE = image_size
        self.create()

    def create(self):
        self.L1 = fc(self.X, self.WORD2VEC_SIZE, (self.IMAGE_SIZE * self.IMAGE_SIZE * 3) / 2, name='L1', relu=True)
        self.L2 = fc(self.L1, (self.IMAGE_SIZE * self.IMAGE_SIZE * 3) / 2, self.IMAGE_SIZE * self.IMAGE_SIZE * 3,
                     name='L2', relu=False)
        self.final_image = tf.reshape(self.L2, (-1, self.IMAGE_SIZE, self.IMAGE_SIZE, 3))


class VGG19(object):
    """VGG19 model"""
    def __init__(self, x, keep_prob, num_classes):
        self.X = x
        self.KEEP_PROB = keep_prob
        self.NUM_CLASSES = num_classes
        self.create()

    def create(self):
        normalized_images = normalize_images(self.X)

        conv1_1 = conv(normalized_images, 3, 3, 64, 1, 1, padding='SAME', name='conv1_1', batch_norm=True)
        conv1_2 = conv(conv1_1, 3, 3, 64, 1, 1, padding='SAME', name='conv1_2', batch_norm=True)
        pool1 = max_pool(conv1_2, 2, 2, 2, 2, padding='SAME', name='pool1')

        conv2_1 = conv(pool1, 3, 3, 128, 1, 1, padding='SAME', name='conv2_1', batch_norm=True)
        conv2_2 = conv(conv2_1, 3, 3, 128, 1, 1, padding='SAME', name='conv2_2', batch_norm=True)
        pool2 = max_pool(conv2_2, 2, 2, 2, 2, padding='SAME', name='pool2')

        conv3_1 = conv(pool2, 3, 3, 256, 1, 1, padding='SAME', name='conv3_1', batch_norm=True)
        conv3_2 = conv(conv3_1, 3, 3, 256, 1, 1, padding='SAME', name='conv3_2', batch_norm=True)
        conv3_3 = conv(conv3_2, 3, 3, 256, 1, 1, padding='SAME', name='conv3_3', batch_norm=True)
        conv3_4 = conv(conv3_3, 3, 3, 256, 1, 1, padding='SAME', name='conv3_4', batch_norm=True)
        pool3 = max_pool(conv3_4, 2, 2, 2, 2, padding='SAME', name='pool3')

        conv4_1 = conv(pool3, 3, 3, 512, 1, 1, padding='SAME', name='conv4_1', batch_norm=True)
        conv4_2 = conv(conv4_1, 3, 3, 512, 1, 1, padding='SAME', name='conv4_2', batch_norm=True)
        conv4_3 = conv(conv4_2, 3, 3, 512, 1, 1, padding='SAME', name='conv4_3', batch_norm=True)
        conv4_4 = conv(conv4_3, 3, 3, 512, 1, 1, padding='SAME', name='conv4_4', batch_norm=True)
        pool4 = max_pool(conv4_4, 2, 2, 2, 2, padding='SAME', name='pool4')

        flattened_shape = np.prod([s.value for s in pool4.get_shape()[1:]])
        flattened = tf.reshape(pool4, [-1, flattened_shape], name='flatenned')

        fc6 = fc(flattened, flattened_shape, 4096, name='fc6')
        self.fc7 = fc(fc6, 4096, 4096, name='fc7')
        self.fc8 = fc(self.fc7, 4096, self.NUM_CLASSES, relu=False, name='fc8')
