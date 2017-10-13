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
    def __init__(self, x, keep_prob, num_classes, skip_layer, pre_trained_path=None):
        self.X = x
        self.NUM_CLASSES = num_classes
        self.KEEP_PROB = keep_prob
        self.SKIP_LAYER = skip_layer
        self.IS_TRAINING = False
        self.WEIGHTS_PATH = pre_trained_path
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
        dropout3 = dropout(fc3, self.KEEP_PROB)

        # 4th Layer: FC (w ReLu) -> Dropout
        fc4 = fc(dropout3, 384, 192, name = 'fc4')
        dropout4 = dropout(fc4, self.KEEP_PROB)

        # 5th Layer: FC and return unscaled activations
        # (for tf.nn.softmax_cross_entropy_with_logits)
        self.fc5 = fc(dropout4, 192, self.NUM_CLASSES, relu = False, name='fc5')


    def load_pre_trained_weights(self, session):
        weights_dict = np.load(self.WEIGHTS_PATH, encoding = 'bytes').item()

        for op_name in weights_dict:
            if op_name not in self.SKIP_LAYER:
                with tf.variable_scope(op_name, reuse=True):
                    for data in weights_dict[op_name]:
                        if len(data.shape) == 1:
                            var = tf.get_variable('biases', trainable=False)
                            session.run(var.assign(data))
                        else:
                            var = tf.get_variable('weights', trainable=False)
                            session.run(var.assign(data))
