import tensorflow as tf
from helpers.constants import *
from helpers.quantizers import *

class ResBlock(tf.keras.layers.Layer):
	"""
	Convolutional Residual Block for Convolutional Variational Auto-Encoder
	"""
	def __init__(self, out_channels, mid_channels=None, bn=False, name = None):
		super(ResBlock, self).__init__(name = name)

		if mid_channels is None:
			mid_channels = out_channels

		layers = [
			tf.keras.layers.Activation(tf.keras.activations.relu),
			tf.keras.layers.Conv2D(mid_channels, kernel_size = 3, strides = 1, padding = "same", use_bias = True),
			tf.keras.layers.Activation(tf.keras.activations.relu),
			tf.keras.layers.Conv2D(out_channels, kernel_size = 1, strides = 1, padding = "valid", use_bias = True)
		]

		if bn:
			layers.insert(2, tf.keras.layers.BatchNormalization())

		self.convs = tf.keras.Sequential(layers)

	def call(self, x):
		# Residual output
		return x + self.convs(x)


def get_encoder(latent_dim=EMBEDDING_DIM, input_shape=(IMAGE_HEIGHT, IMAGE_WIDTH, 3), num_resblocks = 2, batchnorm = True, name="encoder"):
	"""
	Construct Convolutional Encoder
	Args:
		- latent_dim = EMBEDDING_DIM: embedding size for auto-encoder
		- input_shape = (IMAGE_HEIGHT, IMAGE_WIDTH, 3): shape of input
		- num_resblocks = 2: number of residual convolution blocks
		- batchnorm = True: use of BatchNormalization layers in residual blocks
		- name = "encoder": name of model
	Returns:
		- tensorflow.keras.Model
	"""
	encoder_inputs = tf.keras.Input(shape=input_shape)

	conv1 = tf.keras.layers.Conv2D(latent_dim, 4, strides = 2, padding = "same", use_bias = False)(encoder_inputs)
	conv1 = tf.keras.layers.LeakyReLU()(conv1)
	conv1 = tf.keras.layers.BatchNormalization()(conv1)
	
	conv2 = tf.keras.layers.Conv2D(latent_dim, 4, strides = 2, padding = "same", use_bias = False)(conv1)
	conv2 = tf.keras.layers.LeakyReLU()(conv2)
	conv2 = tf.keras.layers.BatchNormalization()(conv2)
	x = conv2

	for i in range(num_resblocks):
		x = ResBlock(latent_dim, bn = batchnorm, name = f"{name}_resblock{i}")(x)
		if batchnorm:
			x = tf.keras.layers.BatchNormalization()(x)

	return tf.keras.Model(encoder_inputs, x, name=name)


def get_decoder(input_shape, latent_dim=EMBEDDING_DIM, num_resblocks = 2, num_channels = 3, name="decoder"):
	"""
	Constructs Convolutional Decoder
	Args:
		- input_shape: input shape of decoder
		- latent_dim = EMBEDDING_DIM: embedding size for auto-encoder
		- num_resblocks = 2: number of residual convolution blocks
		- num_channels = 3: number of output channels (RGB)
		- name = "decoder": name of model
	Returns:
		- tensorflow.keras.Model
	"""
	decoder_inputs = tf.keras.Input(shape=input_shape)

	x = tf.keras.layers.Conv2D(latent_dim, kernel_size = 4, strides = 1, padding = "same", use_bias = False)(decoder_inputs)

	for i in range(num_resblocks):
		x = ResBlock(latent_dim, name = f"{name}_resblock{i}")(x)

	conv1 = tf.keras.layers.Conv2DTranspose(latent_dim, kernel_size = 4, strides = 2, padding = "same", use_bias = False)(x)
	conv1 = tf.keras.layers.LeakyReLU()(conv1)
	conv1 = tf.keras.layers.BatchNormalization()(conv1)

	conv2 = tf.keras.layers.Conv2DTranspose(latent_dim, kernel_size=4, strides = 2, padding = "same", use_bias = False)(conv1)
	conv2 = tf.keras.layers.LeakyReLU()(conv2)
	conv2 = tf.keras.layers.BatchNormalization()(conv2)

	decoder_outputs = tf.keras.layers.Conv2DTranspose(num_channels, kernel_size=4, padding = "same", use_bias = False)(conv2)

	decoder_outputs = tf.keras.activations.tanh(decoder_outputs)

	return tf.keras.Model(decoder_inputs, decoder_outputs, name=name)

def get_image_vqvae(
		latent_dim=EMBEDDING_DIM,
		num_embeddings=NUM_EMBEDDINGS,
		image_shape=(IMAGE_HEIGHT, IMAGE_WIDTH),
		num_channels = 3,
		ema = True,
		batchnorm = True,
		name = "vq_vae"):
	"""
	Constructs VQ-VAE for Images
	Args:
		- latent_dim = EMBEDDING_DIM: embedding size for auto-encoder
		- num_embeddings = NUM_EMBEDDINGS: number of codes in the codebook
		- image_shape = (IMAGE_HEIGHT, IMAGE_WIDTH): height + width of an image
		- num_channels = 3: number of output channels (RGB)
		- ema = True: use Vector Quantizer Exponential Moving Average or normal
		- batchnorm = True: use Batch Normalization or not
		- name = "vq_vae": name of model
	Returns:
		- tensorflow.keras.Model
	"""
	if ema:
		vq_layer = VectorQuantizerEMA(
			embedding_dim = latent_dim, 
			num_embeddings = num_embeddings,
			commitment_cost=COMMITMENT_COST,
			decay=DECAY,
			name="vector_quantizer")
	else:
		vq_layer = VectorQuantizer(
			embedding_dim = latent_dim, 
			num_embeddings = num_embeddings,
			commitment_cost=COMMITMENT_COST,
			name="vector_quantizer")
	encoder = get_encoder(latent_dim = latent_dim, input_shape=image_shape + (num_channels,), batchnorm=batchnorm)
	inputs = tf.keras.Input(shape=image_shape + (num_channels,))
	encoder.build(image_shape + (num_channels,))
	encoder_outputs = encoder(inputs)
	decoder = get_decoder(encoder.output_shape[1:], latent_dim = latent_dim)
	quantized_latents = vq_layer(encoder_outputs)
	reconstructions = decoder(quantized_latents)
	vq_vae = tf.keras.Model(inputs, reconstructions, name=name)
	vq_vae.build(image_shape + (num_channels,))
	return vq_vae