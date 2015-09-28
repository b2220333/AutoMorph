import settings
import images
import process
import aux

import sys
import os


# Segment uses the bounding box identified by the sharpest image in a
# set of stacks to chop just the edf into individual images

# Started on 3/21/2014 by Yusu Liu
# code uses base code of PM Hull (20-Oct-13)with updates by B. Dobbins, PMH, and Y. Liu
# converted to python by K. Nelson (2015-Sept)


def segment(settings_file):

    version = '2015-8-31'

    runs = settings.parse(settings_file)

    for i, run in enumerate(runs):

        print('Segment - running configuration %d of %d from %s'
              % (i+1, len(runs), settings_file))

        # Get list of images in directory
        target_image_list = images.list_files(run['directory'], run['debug'], run['input_ext'])
        top_image_filename = target_image_list[-1]

        # Set up additonal run parameters

        # Get the microns per pixel for this image: (new, and ugly, modification - Oct. 2014)
        if run['pixel_size_x'] == None:
            print 'No pixel size set in settings file, attempting to read microns per pixel from xml file...'
            run['pixel_size_x'], run['pixel_size_y'] = images.microns_per_pixel_xml(top_image_filename)

        run['units_per_pixel'] = round(run['pixel_size_y'] * 10) / 10.0

        run['image_label'] = aux.contruct_image_label(run, version)

        if not os.path.exists(run['full_output']):
            os.makedirs(run['full_output'])

        # Load and resize top-level image
        top_image = images.load(top_image_filename, run)

        # Identify all objects based on threshold & minimumLight values
        objects = images.find_objects(top_image, run)

        process.save_overview_image(top_image, objects, top_image_filename, run)

        if run['mode'] == 'sample':
            run['image_file_label'] = 'th=%05.4f_size=%04.0fu-%04.0fu' \
                              % (run['threshold'], run['minimumSize'], run['maximumSize'])
            process.sample(top_image, objects, top_image_filename, run)

        elif run['mode'] == 'final':

            print('Saving Settings into %s' % run['full_output'])
            settings.save(run.copy())
            # Loop over the planes we're interested in, load an image, then process it
            for plane_num, plane_image in enumerate(target_image_list[:-2]):
                process.final(plane_image, objects, run, plane_num)


if __name__ == "__main__":

    if len(sys.argv) == 2:
        segment(sys.argv[1])

    else:
        print 'Usage: segment <settings_file>'
        sys.exit('Error: incorrect usage')
