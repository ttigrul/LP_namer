import bpy
import re
from collections import defaultdict

def set_shade_smooth(obj):
    """
    Включает shade smooth для объекта и устанавливает авто-сглаживание.
    """
    if obj.type == 'MESH':
        bpy.context.view_layer.objects.active = obj  # Делаем объект активным

        # Переключаемся в режим редактирования
        bpy.ops.object.mode_set(mode='EDIT')

        # Применяем shade smooth ко всем граням
        bpy.ops.mesh.faces_shade_smooth()

        # Возвращаемся в режим объекта
        bpy.ops.object.mode_set(mode='OBJECT')

        # Устанавливаем авто-сглаживание для всех полигонов
        mesh = obj.data
        if hasattr(mesh, 'use_auto_smooth'):
            mesh.use_auto_smooth = True  # Включаем авто-сглаживание
        if hasattr(mesh, 'auto_smooth_angle'):
            mesh.auto_smooth_angle = 3.14159  # Устанавливаем угол сглаживания на 180 градусов (в радианах)

def rename_objects(objects):
    """
    Переименовывает объекты, добавляя числовой префикс и удаляя суффиксы.
    """
    name_groups = defaultdict(list)
    for obj in objects:
        # Удаляем суффикс .XXX из имени объекта
        base_name = re.sub(r'\.\d{3}$', '', obj.name)
        name_groups[base_name].append(obj)

    for base_name, group in name_groups.items():
        # Сортируем объекты внутри группы по числовому суффиксу
        group.sort(key=lambda o: int(re.search(r'\.(\d{3})$', o.name).group(1)) if re.search(r'\.\d{3}$', o.name) else 0)
        for i, obj in enumerate(group, start=1):
            # Переименовываем объекты с добавлением префикса
            obj.name = f"{i}_{base_name}"

def apply_modifiers(objects):
    """
    Применяет модификаторы к объектам, снижая их разрешение.
    """
    for obj in objects:
        bpy.context.view_layer.objects.active = obj  # Делаем объект активным
        for modifier in obj.modifiers:
            if modifier.type in {'MULTIRES', 'SUBSURF'}:
                modifier.levels = 1
                modifier.render_levels = 1
                if modifier.type == 'MULTIRES':
                    modifier.sculpt_levels = 1
                else:
                    modifier.quality = 1

            if modifier.type == 'SOLIDIFY':
                bpy.ops.object.modifier_apply(modifier=modifier.name)  # Применяем модификатор Solidify

def make_single_user_objects(objects):
    """
    Делает объекты и данные уникальными, если они используются несколькими объектами.
    """
    for obj in objects:
        if obj.data.users > 1:
            obj.data = obj.data.copy()  # Копируем данные меша, если они используются более чем одним объектом
        if obj.users > 1:
            bpy.context.view_layer.objects.active = obj
            bpy.ops.object.make_single_user(object=True, object_data=True)  # Делаем объект уникальным

def save_and_remove_linked_object_data(objects):
    """
    Сохраняет и удаляет ссылки на данные объектов для восстановления после применения модификаторов.
    """
    linked_objects = {}
    for obj in objects:
        if obj.data.users > 1:
            # Находим все объекты, которые используют те же данные
            linked_objects[obj] = [o for o in bpy.data.objects if o.data == obj.data]
            for linked_obj in linked_objects[obj]:
                if linked_obj != obj:
                    # Создаем копию данных для связанных объектов
                    linked_obj.data = linked_obj.data.copy()
    return linked_objects

def restore_linked_object_data(linked_objects, original_to_duplicate):
    """
    Восстанавливает связи между объектами после применения модификаторов.
    """
    for original, linked_objs in linked_objects.items():
        duplicate_original = original_to_duplicate.get(original, None)
        if duplicate_original:
            for linked_obj in linked_objs:
                duplicate_linked = original_to_duplicate.get(linked_obj, None)
                if duplicate_linked:
                    duplicate_linked.data = duplicate_original.data  # Восстанавливаем связи с данными

def duplicate_and_modify_meshes(collection, max_objects=None):
    """
    Дублирует и модифицирует меши в коллекции, затем применяет к ним Shade Smooth.
    """
    # Получаем все объекты типа MESH в коллекции
    mesh_objects = [obj for obj in collection.objects if obj.type == 'MESH']
    
    # Переименовываем объекты
    rename_objects(mesh_objects)

    # Ограничиваем количество объектов, если указано max_objects
    if max_objects is not None:
        mesh_objects = mesh_objects[:max_objects]

    original_to_duplicate = {}
    duplicates = []

    # Сохраняем и удаляем ссылки на данные объектов
    linked_objects = save_and_remove_linked_object_data(mesh_objects)

    for obj in mesh_objects:
        if obj.data.users > 1:
            mesh_data_copy = obj.data.copy()  # Копируем данные меша для дубликата
            duplicate = obj.copy()
            duplicate.data = mesh_data_copy
        else:
            duplicate = obj.copy()  # Копируем объект и данные меша

        collection.objects.link(duplicate)  # Добавляем дубликат в ту же коллекцию
        obj.hide_set(True)  # Скрываем оригинал

        # Определяем префикс по имени оригинала
        prefix = re.search(r'^(\d+)_', obj.name).group(1)
        base_name = re.sub(r'^\d+_', '', obj.name)
        new_name = f"{prefix}_{base_name}_LP"
        duplicate.name = new_name  # Присваиваем новое имя дубликату

        duplicates.append(duplicate)
        original_to_duplicate[obj] = duplicate

    make_single_user_objects(duplicates + mesh_objects)  # Делаем объекты уникальными
    apply_modifiers(duplicates + mesh_objects)  # Применяем модификаторы
    
    # Восстанавливаем связи между оригиналами и дубликатами
    restore_linked_object_data(linked_objects, original_to_duplicate)

    # Применяем shade smooth ко всем объектам в коллекции после всех манипуляций
    for obj in duplicates + mesh_objects:
        set_shade_smooth(obj)

# Получаем активную коллекцию
active_collection = bpy.context.view_layer.active_layer_collection.collection

# Проверка на наличие объектов в активной коллекции
if len(active_collection.objects) > 0:
    duplicate_and_modify_meshes(active_collection)
else:
    print("Нет объектов в активной коллекции.")
