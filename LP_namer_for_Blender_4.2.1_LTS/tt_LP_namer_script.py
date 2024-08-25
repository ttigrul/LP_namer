import bpy
import re
from collections import defaultdict

def rename_objects(objects):
    """
    Переименовывает объекты, добавляя префикс X_ (числовой) и удаляя суффикс .XXX.
    """
    name_groups = defaultdict(list)

    # Группируем объекты по имени без суффикса .XXX
    for obj in objects:
        base_name = re.sub(r'\.\d{3}$', '', obj.name)
        name_groups[base_name].append(obj)

    # Переименовываем объекты внутри каждой группы
    for base_name, group in name_groups.items():
        group.sort(key=lambda o: int(re.search(r'\.(\d{3})$', o.name).group(1)) if re.search(r'\.\d{3}$', o.name) else 0)
        for i, obj in enumerate(group, start=1):
            obj.name = f"{i}_{base_name}"

def apply_modifiers(objects):
    """
    Применяет модификаторы к уникальным объектам.
    """
    for obj in objects:
        bpy.context.view_layer.objects.active = obj

        # Применяем модификаторы
        for modifier in obj.modifiers:
            if modifier.type in {'MULTIRES', 'SUBSURF'}:
                modifier.levels = 1
                modifier.render_levels = 1
                if modifier.type == 'MULTIRES':
                    modifier.sculpt_levels = 1
                else:
                    modifier.quality = 1

            # Применяем модификатор Solidify
            if modifier.type == 'SOLIDIFY':
                bpy.ops.object.modifier_apply(modifier=modifier.name)

def make_single_user_objects(objects):
    """
    Делает объекты и данные уникальными.
    """
    for obj in objects:
        # Делаем данные объекта уникальными, если они используются несколькими объектами
        if obj.data.users > 1:
            obj.data = obj.data.copy()

        # Делаем сам объект уникальным, если он используется несколькими объектами
        if obj.users > 1:
            bpy.context.view_layer.objects.active = obj
            bpy.ops.object.make_single_user(object=True, object_data=True)

def save_and_remove_linked_object_data(objects):
    """
    Сохраняет и удаляет ссылки на данные объектов для восстановления после применения модификаторов.
    """
    linked_objects = {}
    for obj in objects:
        if obj.data.users > 1:
            linked_objects[obj] = [o for o in bpy.data.objects if o.data == obj.data]
            for linked_obj in linked_objects[obj]:
                if linked_obj != obj:
                    linked_obj.data = linked_obj.data.copy()  # Создаем уникальные данные для связанных объектов
    return linked_objects

def restore_linked_object_data(linked_objects, original_to_duplicate):
    """
    Восстанавливает связи между объектами после применения модификаторов.
    """
    for original, linked_objs in linked_objects.items():
        # Получаем дубликаты для восстановленных объектов
        duplicate_original = original_to_duplicate.get(original, None)
        if duplicate_original:
            for linked_obj in linked_objs:
                duplicate_linked = original_to_duplicate.get(linked_obj, None)
                if duplicate_linked:
                    duplicate_linked.data = duplicate_original.data

def duplicate_and_modify_meshes(collection, max_objects=None):
    # Получаем все объекты в выбранной коллекции
    mesh_objects = [obj for obj in collection.objects if obj.type == 'MESH']
    
    # Переименовываем оригинальные объекты
    rename_objects(mesh_objects)

    # Если max_objects не None, ограничиваем количество обрабатываемых объектов
    if max_objects is not None:
        mesh_objects = mesh_objects[:max_objects]

    # Создаем списки для дубликатов и их оригиналов
    original_to_duplicate = {}
    duplicates = []

    # Сохраняем и удаляем ссылки на данные объектов
    linked_objects = save_and_remove_linked_object_data(mesh_objects)

    for obj in mesh_objects:
        # Создаем уникальные данные меша для дубликата, если объект использует общие данные
        if obj.data.users > 1:
            mesh_data_copy = obj.data.copy()  # Копируем данные меша для дубликата
            duplicate = obj.copy()
            duplicate.data = mesh_data_copy
        else:
            duplicate = obj.copy()  # Копируем объект и данные меша

        collection.objects.link(duplicate)  # Привязываем дубликат к той же коллекции

        # Скрываем оригинал
        obj.hide_set(True)

        # Определяем префикс по имени оригинала
        prefix = re.search(r'^(\d+)_', obj.name).group(1)

        # Модифицируем имя дубликата
        base_name = re.sub(r'^\d+_', '', obj.name)
        new_name = f"{prefix}_{base_name}_LP"
        duplicate.name = new_name

        # Добавляем дубликат в список для дальнейшей обработки
        duplicates.append(duplicate)

        # Связываем дубликаты с оригиналами
        original_to_duplicate[obj] = duplicate

    # Делает данные объектов уникальными
    make_single_user_objects(duplicates + mesh_objects)

    # Применяем модификаторы к уникальным объектам
    apply_modifiers(duplicates + mesh_objects)
    
    # Применяем настройки Shade Smooth
    for obj in duplicates + mesh_objects:
        set_shade_smooth(obj)

    # Восстанавливаем связи между оригиналами и дубликатами
    restore_linked_object_data(linked_objects, original_to_duplicate)

    def set_shade_smooth(obj):
    """
    Включает shade smooth для объекта и устанавливает авто-сглаживание.
    """
    if obj.type == 'MESH':
        bpy.context.view_layer.objects.active = obj

        # Переключаем в режим редактирования
        bpy.ops.object.mode_set(mode='EDIT')

        # Применяем shade smooth ко всем граням
        bpy.ops.mesh.faces_shade_smooth()

        # Возвращаемся в режим объекта
        bpy.ops.object.mode_set(mode='OBJECT')

        # Устанавливаем авто-сглаживание для всех полигонами
        mesh = obj.data
        if hasattr(mesh, 'use_auto_smooth'):
            mesh.use_auto_smooth = True  # Устанавливаем авто-сглаживание
        if hasattr(mesh, 'auto_smooth_angle'):
            mesh.auto_smooth_angle = 3.14159  # 180 градусов в радианах

# Получаем активную коллекцию
active_collection = bpy.context.view_layer.active_layer_collection.collection

# Проверка на наличие объектов в активной коллекции
if len(active_collection.objects) > 0:
    # Выполняем функцию без лимита на количество объектов
    duplicate_and_modify_meshes(active_collection)
else:
    print("Нет объектов в активной коллекции.")

