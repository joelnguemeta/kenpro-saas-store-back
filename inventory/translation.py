from modeltranslation.translator import TranslationOptions, register

from .models import Category, Location, Product, ProductContent, ProductVariant


@register(Category)
class CategoryTranslationOptions(TranslationOptions):
    fields = ("name",)


@register(Product)
class ProductTranslationOptions(TranslationOptions):
    fields = ("name",)


@register(ProductVariant)
class ProductVariantTranslationOptions(TranslationOptions):
    fields = ("name",)


@register(ProductContent)
class ProductContentTranslationOptions(TranslationOptions):
    fields = ("long_description", "seo_title", "seo_description")


@register(Location)
class LocationTranslationOptions(TranslationOptions):
    fields = ("name",)
