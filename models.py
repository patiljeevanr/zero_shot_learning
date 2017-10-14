#Based on https://kratzert.github.io/2017/02/24/finetuning-alexnet-with-tensorflow.html

import tensorflow as tf
import numpy as np


#Convolution function that can be split in multiple GPUS
def conv(x, filter_height, filter_width, num_filters, stride_y, stride_x, name,
             padding='SAME', groups=1, verbose_shapes=False):

    #Get number of input chennels
    input_channels = int(x.get_shape()[-1])

    if verbose_shapes:
        print('INPUT_CHANNELS', input_channels)
        print('X SHAPE conv', x.get_shape())

    convolve = lambda i, k: tf.nn.conv2d(i, k, strides = [1, stride_y, stride_x, 1],
                                          padding = padding)

    with tf.variable_scope(name) as scope:
        weights = tf.get_variable('weights', shape = [filter_height, filter_width, input_channels/groups, num_filters], trainable=True)
        biases = tf.get_variable('biases',shape=[num_filters], trainable=True)

        if groups == 1:
            conv = convolve(x, weights)
        else:
            input_groups = tf.split(axis=3, num_or_size_splits=groups, value=x)
            weight_groups = tf.split(axis=3, num_or_size_splits=groups, value=weights)
            output_groups = [convolve(i, k) for i, k in zip(input_groups, weight_groups)]

            conv = tf.concat(axis=3, values=output_groups)

        bias = tf.reshape(tf.nn.bias_add(conv, biases), conv.get_shape().as_list())
        relu = tf.nn.relu(bias, name = scope.name)

        return relu

#Full connected layer
def fc(x, num_in, num_out, name, relu=True):
    with tf.variable_scope(name) as scope:
        weights = tf.get_variable('weights', shape=[num_in, num_out], trainable=True)
        biases = tf.get_variable('biases', [num_out], trainable=True)

        act = tf.nn.xw_plus_b(x, weights, biases, name=scope.name)

        if relu == True:
            relu = tf.nn.relu(act)
            return relu
        else:
            return act

#Max pooling layer
def max_pool(x, filter_height, filter_width, stride_y, stride_x,
                name, padding='SAME', verbose_shapes=False):
    if verbose_shapes:
        print('X SHAPE maxpool', x.get_shape())

    return tf.nn.max_pool(x, ksize=[1, filter_height, filter_width, 1],
                              strides = [1,stride_y, stride_x, 1],
                              padding = padding, name = name)

#Batch normalization
def lrn(x, radius, alpha, beta, name, bias=1.0, verbose_shapes=False):
    if verbose_shapes:
        print('X SHAPE lrn', x.get_shape())

    return tf.nn.local_response_normalization(x, depth_radius = radius,
                                                  alpha = alpha, beta = beta,
                                                  bias = bias, name = name)

def normalize_images(x):
    return tf.map_fn(lambda frame: tf.image.per_image_standardization(frame), x)
    
#Dropout layer
def dropout(x, keep_prob):
    return tf.nn.dropout(x, keep_prob)

class AlexNet(object):
    def __init__(self, x, num_classes):
        self.X = x
        self.NUM_CLASSES = num_classes
        self.create()

    def create(self):
        # 1st Layer: Conv (w ReLu) -> Lrn -> Pool
        normalized_images = normalize_images(self.X)
        conv1 = conv(normalized_images, 5, 5, 64, 1, 1, padding = 'VALID', name = 'conv1')
        norm1 = lrn(conv1, 2, 2e-05, 0.75, name = 'norm1')
        pool1 = max_pool(norm1, 3, 3, 2, 2, padding = 'VALID', name = 'pool1')

        # 2nd Layer: Conv (w ReLu) -> Lrn -> Poolwith 2 groups
        conv2 = conv(pool1, 5, 5, 64, 1, 1, groups = 2, name = 'conv2')
        norm2 = lrn(conv2, 2, 2e-05, 0.75, name = 'norm2')
        pool2 = max_pool(norm2, 3, 3, 2, 2, padding = 'VALID', name ='pool2')

        # 3th Layer: Flatten -> FC (w ReLu) -> Dropout
        flattened = tf.reshape(pool2, [-1, 4*4*64])
        fc3 = fc(flattened, 4*4*64, 384, name='fc3')
        
        # 4th Layer: FC (w ReLu) -> Dropout
        fc4 = fc(fc3, 384, 192, name = 'fc4')
        
        # 5th Layer: FC and return unscaled activations
        # (for tf.nn.softmax_cross_entropy_with_logits)
        self.fc5 = fc(fc4, 192, self.NUM_CLASSES, relu = False, name='fc5')

class VGG11(object):
    def __init__(self, x, keep_prob, num_classes):
        self.X = x
        self.KEEP_PROB = keep_prob
        self.NUM_CLASSES = num_classes
        self.create()

    def create(self):
        normalized_images = normalize_images(self.X)

        #1st Layer: Conv (w ReLu) -> Pool
        conv1 = conv(normalized_images, 3, 3, 64, 1, 1, padding = 'VALID', name = 'conv1')
        pool1 = max_pool(conv1, 2, 2, 2, 2, padding = 'VALID', name = 'pool1')
        
        #2nd Layer: Conv (w ReLu) -> Pool
        conv2 = conv(pool1, 3, 3, 128, 1, 1, padding = 'VALID', name = 'conv2')
        pool2 = max_pool(conv2, 2, 2, 2, 2, padding = 'VALID', name = 'pool2')

        #3rd Layer: Conv (w ReLu) -> Conv (w ReLu) -> Pool
        conv3 = conv(pool2, 3, 3, 256, 1, 1, padding = 'VALID', name = 'conv3')
        conv4 = conv(conv3, 3, 3, 256, 1, 1, padding = 'VALID', name = 'conv4')
        pool3 = max_pool(conv4, 2, 2, 2, 2, padding = 'VALID', name = 'pool3')

        #4th Layer: Conv (w ReLu) -> Conv (w ReLu) -> Pool
        conv5 = conv(pool3, 3, 3, 512, 1, 1, padding = 'VALID', name = 'conv5')
        conv6 = conv(conv5, 3, 3, 512, 1, 1, padding = 'VALID', name = 'conv6')
        pool4 = max_pool(conv6, 2, 2, 2, 2, padding = 'VALID', name = 'pool4')

        num_elems = int(np.prod(pool4.get_shape()[1:]))
        
        #5th Layer: Full connecteds
        flattened = tf.reshape(pool4, [-1, num_elems])
        fc7 = fc(flattened, num_elems, 4096, name='fc7')
        dropout8 = dropout(fc7, self.KEEP_PROB)
        fc8 = fc(dropout8, 4096, 4096, name='fc8')
        dropout9 = dropout(fc8, self.KEEP_PROB)

        self.fc9 = fc(dropout9, 4096, self.NUM_CLASSES, relu = False, name = 'fc9')
