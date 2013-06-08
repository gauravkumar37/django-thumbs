# -*- encoding: utf-8 -*-
"""
django-thumbs on-the-fly
https://github.com/madmw/django-thumbs

A fork of django-thumbs [http://code.google.com/p/django-thumbs/] by Antonio Melé [http://django.es].

"""
from django.conf import settings
from django.conf.global_settings import INSTALLED_APPS
from django.core.files.base import ContentFile
from django.db.models import ImageField
from django.db.models.fields.files import ImageFieldFile
from os.path import join, normpath
import cStringIO

try:
    from PIL import Image, ImageOps
except:
    # Mac OS X
    import Image, ImageOps

def generate_thumb(original, size, preserve_ratio, format='JPEG'):
    """
    Generates a thumbnail image and returns a ContentFile object with the thumbnail

    Arguments:
    original -- The image being resized as `File`.
    size     -- Desired thumbnail size as `tuple`. Example: (70, 100)
    preserve_ratio    -- True for resizing the image, False for cropping the image
    format   -- Format of the original image ('JPEG', 'PNG', ...) The thumbnail will be generated using this same format.

    """
    original.seek(0)  # see http://code.djangoproject.com/ticket/8222 for details
    image = Image.open(original)
    if image.mode not in ('L', 'RGB', 'RGBA'):
        image = image.convert('RGB')
    if preserve_ratio:
        # resize the image
        image.thumbnail(size, Image.ANTIALIAS)
    else:
        # crop the image the fit the size specified
        image = ImageOps.fit(image, size, Image.ANTIALIAS)
    io = cStringIO.StringIO()
    if format.upper() == 'JPG':
        format = 'JPEG'
    image.save(io, format)
    return ContentFile(io.getvalue())

class ImageWithThumbsFieldFile(ImageFieldFile):
    """Django `ImageField` replacement with automatic generation of thumbnail images.
       See `ImageWithThumbsField` for usage example.

    """

    THUMB_SUFFIX = '%s.%sx%s.%s'

    def __init__(self, *args, **kwargs):
        super(ImageFieldFile, self).__init__(*args, **kwargs)

    def _url_for_size(self, size):
        """Return a URL pointing to the thumbnail image of the requested size.
        If `settings.THUMBS_GENERATE_MISSING_THUMBNAILS` is True, the thumbnail will be created if it doesn't exist on disk.
            
        Arguments:
        size  -- A tuple with the desired width and height. Example: (100, 100)

        """
        if not self:
            return ''
        else:
            # generate missing thumbnail if needed
            fileBase, extension = self.name.rsplit('.', 1)
            thumb_file = self.THUMB_SUFFIX % (fileBase, size[0], size[1], extension)
            if settings.THUMBS_GENERATE_MISSING_THUMBNAILS:
                if not self.storage.exists(thumb_file):
                    try:
                        self._generate_thumb(self.storage.open(self.name), size)
                    except:
                        if settings.DEBUG:
                            import sys
                            print "Exception generating thumbnail"
                            print sys.exc_info()
            urlBase, extension = self.url.rsplit('.', 1)
            thumb_url = self.THUMB_SUFFIX % (urlBase, size[0], size[1], extension)
            return thumb_url

    def __getattr__(self, name):
        """Return the url for the requested size.

        Arguments:
        name -- The field `url` with size suffix formatted as _WxH. Example: instance.url_100x70

        """
        if not "url_" in name:
            return getattr(super(ImageFieldFile), name)
        sizeStr = name.replace("url_", "")
        width, height = sizeStr.split("x")
        requestedSize = (int(width), int(height))
        acceptedSize = None
        if settings.THUMBS_GENERATE_ANY_SIZE:
            acceptedSize = requestedSize
        else:
            for configuredSize in self.field.sizes:
                # FIXME: fuzzy search, accept nearest size
                if requestedSize == configuredSize:
                    acceptedSize = requestedSize
        if acceptedSize is not None:
            return self._url_for_size(acceptedSize)
        raise ValueError("The requested thumbnail size %s doesn't exist" % sizeStr)

    def _generate_thumb(self, image, size):
        """Generates a thumbnail of `size`.
        
        Arguments:
        image -- An `File` object with the image in its original size.
        size  -- A tuple with the desired width and height. Example: (100, 100)
        
        Returns:
        The actual file name of the saved thumbnail
        """
        # change the upload_to directory to support a different directory for storing thumbnails
        self.name = normpath(join(self.field.upload_thumb_to, self.name[self.name.find('/') + 1:]))
        base, extension = self.name.rsplit('.', 1)
        thumb_name = self.THUMB_SUFFIX % (base, size[0], size[1], extension)
        thumbnail = generate_thumb(image, size, self.field.preserve_ratio, extension)
        saved_as = self.storage.save(thumb_name, thumbnail)
        if thumb_name != saved_as:
            print('Warning while saving thumbnail: There is already a file named %s. New file saved as %s' % (thumb_name, saved_as))
        return saved_as

    def save(self, name, content, save=True):
        super(ImageFieldFile, self).save(name, content, save)
        if settings.DEBUG:
            print('Original image saved at ' + self.name)
        if settings.THUMBS_GENERATE_THUMBNAILS:
            if self.field.sizes:
                for size in self.field.sizes:
                    saved_thumb_as = self._generate_thumb(content, size)
                    if settings.DEBUG:
                        print('Thumbnail image saved at ' + saved_thumb_as)

    def delete(self, save=True):
        if self.name and self.field.sizes:
            for size in self.field.sizes:
                base, extension = self.name.rsplit('.', 1)
                thumb_name = self.THUMB_SUFFIX % (base, size[0], size[1], extension)
                try:
                    self.storage.delete(thumb_name)
                except:
                    if settings.DEBUG:
                        import sys
                        print "Exception deleting thumbnails"
                        print sys.exc_info()
        super(ImageFieldFile, self).delete(save)

    def generate_thumbnails(self):
        """
        """
        if self.field.sizes:
            for size in self.field.sizes:
                try:
                    self._generate_thumb(self.storage.open(self.name), size)
                except:
                    if settings.DEBUG:
                        import sys
                        print "Exception generating thumbnail"
                        print sys.exc_info()

    def thumbnail(self, widthOrSize, height=None):
        """
        Return the thumbnail url for an specific size. The same thing as url_[width]x[height] without the magic.

        Arguments:
        widthOrSize -- Width as integer or size as tuple.
        height      -- Height as integer. Optional, will use `widthOrSize` as height if missing.

        Usage:
        instance.thumbnail(48, 48)
        instance.thumbnail(64)
        instance.thumbnail( (100, 70) )

        """
        if type(widthOrSize) is tuple:
            size = widthOrSize
        else:
            if height is None:
                height = widthOrSize
            size = (widthOrSize, height)
        return self.__getattr__('url_%sx%s' % (size[0], size[1]))


class ImageWithThumbsField(ImageField):
    """
    Usage example:
    ==============
    photo = ImageWithThumbsField(upload_to='images', sizes=((125,125),(300,200),)
    
    To retrieve image URL, exactly the same way as with ImageField:
        my_object.photo.url
    To retrieve thumbnails URL's just add the size to it:
        my_object.photo.url_125x125
        my_object.photo.url_300x200
    
    Note: The 'sizes' attribute is not required. If you don't provide it,
    ImageWithThumbsField will act as a normal ImageField
        
    How it works:
    =============
    For each size in the 'sizes' atribute of the field it generates a
    thumbnail with that size and stores it following this format:
    
    available_filename.[width]x[height].extension

    Where 'available_filename' is the available filename returned by the storage
    backend for saving the original file.
    
    Following the usage example above: For storing a file called "photo.jpg" it saves:
    photo.jpg          (original file)
    photo.125x125.jpg  (first thumbnail)
    photo.300x200.jpg  (second thumbnail)
    
    With the default storage backend if photo.jpg already exists it will use these filenames:
    photo_.jpg
    photo_.125x125.jpg
    photo_.300x200.jpg
    
    Note: django-thumbs assumes that if filename "any_filename.jpg" is available
    filenames with this format "any_filename.[widht]x[height].jpg" will be available, too.
    
    """
    attr_class = ImageWithThumbsFieldFile

    def __init__(self, verbose_name=None, name=None, width_field=None, height_field=None, sizes=None, preserve_ratio=None, upload_thumb_to=None, ** kwargs):
        self.verbose_name = verbose_name
        self.name = name
        self.width_field = width_field
        self.height_field = height_field
        self.sizes = sizes
        if preserve_ratio is None:
            preserve_ratio = settings.THUMBS_PRESERVE_RATIO
        self.preserve_ratio = preserve_ratio
        if upload_thumb_to is None:
            self.upload_thumb_to = kwargs['upload_to']
        else:
            self.upload_thumb_to = upload_thumb_to
        super(ImageField, self).__init__(**kwargs)

# Add south custom field introspection rules to support database migration only if south is present and available
try:
    import south
except ImportError:
    south = None
if south is not None and 'south' in settings.INSTALLED_APPS:
    from south.modelsinspector import add_introspection_rules
    add_introspection_rules([], ["^django_thumbs\.db\.models\.ImageWithThumbsField"])
