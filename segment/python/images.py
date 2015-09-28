from aux import debug_msg

import xml.etree.ElementTree as xml_tree
from skimage.measure import regionprops
from PIL import Image, ImageFont, ImageDraw, TiffImagePlugin

import numpy as np
from scipy import ndimage
import time
import glob
import math
import os


def load(filename, run):
    '''
    Load image from given path and resizes it.
    '''

    start = time.time()

    img = Image.open(filename)

    scaled_img = resize(img, filename, run)

    end = time.time()
    debug_msg('INFO: images.load() processed %s ( %f seconds)' % (filename, end-start), run['debug'] >= 1)

    return scaled_img


def save(image, filename, tags=''):

    if isinstance(image, (np.ndarray, np.generic)):
        image = Image.fromarray(np.uint8(image))

    if tags:
        image.save(filename, tiffinfo=tags)
    else:
        image.save(filename)


def add_comment(filename, comment):

    tags = TiffImagePlugin.ImageFileDirectory()
    tags[270] = comment
    tags.tagtype['Description'] = 2

    Image.DEBUG = False
    TiffImagePlugin.WRITE_LIBTIFF = True

    return tags


def list_files(directory, verbosity, file_extension):
    '''
    This function takes a directory and returns a list of all TIF images in that
    directory
    '''

    file_list = glob.glob(directory+os.sep+"*."+file_extension)

    if verbosity >= 1:
        num_files = len(file_list)

        debug_msg('INFO: images.find() found %d files' % num_files, True)

    return file_list


def resize(img, filename, run):
    '''
    Scales image based on microns per pixel
    '''

    x_image, y_image = img.size
    # Calculate the new dimensions

    scale_factor_x = run['units_per_pixel'] / run['pixel_size_x']
    scale_factor_y = run['units_per_pixel'] / run['pixel_size_y']

    m_resized = int(math.ceil(scale_factor_x * x_image))
    n_resized = int(math.ceil(scale_factor_y * y_image))

    return img.resize((m_resized, n_resized), Image.ANTIALIAS)


def crop(image, box):

    if isinstance(image, (np.ndarray, np.generic)):
        image = Image.fromarray(np.uint8(image))

    image_subsample = image.crop(box)

    return image_subsample


def find_objects(img, run):

    # Make image black and white
    bw_img = img.convert('L')
    bw_img = np.array(bw_img)
    # Pixel range is 0...255
    bw_img[bw_img < 255*run['threshold']] = 0     # Black
    bw_img[bw_img >= 255*run['threshold']] = 255  # White

    # and fill holes
    bw_filled_img = ndimage.morphology.binary_fill_holes(bw_img)

    # label connected objects
    connected_objs, n = ndimage.measurements.label(bw_filled_img)

    # Create list of bounding boxes and filled
    region_list = regionprops(connected_objs)
    num_objects = len(region_list)

    bounding_boxes = [region.bbox for region in region_list]

    # Extract the size of the bounding box into arrays
    size_x = np.array([box[2]-box[0] for box in bounding_boxes])
    size_y = np.array([box[3]-box[1] for box in bounding_boxes])

    minimum_size = run['minimumSize'] / run['units_per_pixel']
    maximum_size = run['maximumSize'] / run['units_per_pixel']

    minimum_size = math.sqrt((minimum_size * maximum_size) / 2.)
    mask = ((size_x > minimum_size) & (size_x < maximum_size) &
            (size_y > minimum_size) & (size_y < maximum_size))

    box_list = np.array(bounding_boxes)
    box_list = box_list[mask]

    box_list = expand_bounding_box(box_list, 0.20, connected_objs.shape)

    debug_msg('INFO: findObjects -> %d total [ Thresh: %f ] -->  %d valid'
              % (n, run['threshold'], len(box_list)), run['debug'] >= 1)

    return box_list


def border(image, border_size):
    '''
    No longer used. Can be deleted
    '''

    width, height = image.size
    image = np.array(image)  # y, x, color

    # Top, Bottom, Left, Right
    image[:round(height * border_size), :, :] = 0
    image[height-round(height * border_size * 6):height, :, :] = 0
    image[:, :round(width * border_size), :] = 0
    image[:, width-round(width * border_size):width, :] = 0

    return Image.fromarray(np.uint8(image))


def add_label_area(image):

    image = np.array(image)

    width = np.shape(image)[1]

    label_area = np.empty([160, width, 3])
    label_area.fill(255)

    image = np.vstack((image, label_area))

    return Image.fromarray(np.uint8(image))


def label_image(orig_image, orig_filename, description, run):

    orig_height = orig_image.size[1]

    image = add_label_area(orig_image)

    mid_x = image.size[0]/2
    draw = ImageDraw.Draw(image)

    # Draw scale bars
    bar_in_pixels_25 = 25 / run['units_per_pixel']
    bar_in_pixels_100 = bar_in_pixels_25 * 4.

    y_100 = orig_height+15
    y_25 = y_100 + 10
    width = 2

    start_100_x = int(mid_x - bar_in_pixels_100/2)
    start_25_x = int(mid_x - bar_in_pixels_25/2)

    draw.line((start_100_x, y_100, start_100_x + bar_in_pixels_100, y_100), fill='black', width=width)
    draw.line((start_25_x, y_25, start_25_x + bar_in_pixels_25, y_25), fill='black', width=width)

    font = set_fontsize(10)
    draw.text((start_100_x+bar_in_pixels_100+10, y_100 - 4), '100 microns', fill='black', font=font)
    draw.text((start_25_x+bar_in_pixels_25+10, y_25 - 4), '25 microns', fill='black', font=font)

    orig_filename = os.path.basename(orig_filename)

    label = run['image_label'][:]
    label.insert(0, description)
    label.append('File: %s' % orig_filename)

    text_y = y_25 + 10 + np.array([0, 20, 40, 70, 85, 100, 115])
    text_size = [14, 14, 14, 9, 9, 9, 9]

    for i, line in enumerate(label):
        font = set_fontsize(text_size[i])
        w, h = draw.textsize(line, font=font)
        new_x = (mid_x*2 - w)/2
        draw.text((new_x, text_y[i]), line, fill='black', font=font)

    return image, label


def set_fontsize(font_size):

    font_path = os.path.dirname(os.path.realpath(__file__))+os.sep+'OpenSans-Regular.ttf'
    return ImageFont.truetype(font_path, font_size)


def draw_bounding_boxes(image, box_list):

    draw = ImageDraw.Draw(image)

    # Mark the bounding boxes of all objects
    for i, box in enumerate(box_list):
        y1 = math.ceil(box[0])
        x1 = math.ceil(box[1])
        y2 = math.ceil(box[2])
        x2 = math.ceil(box[3])

        draw.line([x1, y2, x2, y2], fill='red', width=20)
        draw.line([x1, y1, x2, y1], fill='red', width=20)
        draw.line([x1, y1, x1, y2], fill='red', width=20)
        draw.line([x2, y1, x2, y2], fill='red', width=20)

        font = set_fontsize(40)
        draw.text((x2+40, y2), str(i+1), fill='red', font=font)

    return image


def expand_bounding_box(box_list, scale_factor, i_size):

    num_boxes = len(box_list)

    for i, bounding_box in enumerate(box_list):
        width = bounding_box[3]-bounding_box[1]
        height = bounding_box[2]-bounding_box[0]

        # bounding_box -> (min_row, min_col, max_row, max_col)
        new_top = bounding_box[0] - round(height * scale_factor)
        if new_top < 1:
            new_top = 1

        new_left = bounding_box[1] - round(width * scale_factor)
        if new_left < 1:
            new_left = 1

        new_bottom = bounding_box[2] + round(height * scale_factor)
        if new_bottom > i_size[0]:
            new_bottom = i_size[0] - new_top - 1

        new_right = bounding_box[3] + round(width * scale_factor)
        if new_right > i_size[1]:
            new_right = i_size[1] - new_left - 1

        new_box = [new_top, new_left, new_bottom, new_right]
        box_list[i] = new_box

    return box_list


def microns_per_pixel_xml(filename):

    xml_name = os.path.splitext(filename)[0]+'.xml'
    # Get the microns-per-pixel values:
    root = xml_tree.parse(xml_name).getroot()

    sub_root = root.findall('Calibration')[0]
    x = float(sub_root.findtext('MicronsPerPixelX'))
    y = float(sub_root.findtext('MicronsPerPixelY'))

    return x, y
