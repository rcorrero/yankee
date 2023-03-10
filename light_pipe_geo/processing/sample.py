__author__ = "Richard Correro (richard@richardcorrero.com)"


__doc__ = """
This module contains the definition of `LightPipeSample`, a key component of the
Light-Pipe API. `LightPipeSample` instances are the fundamental unit of data
which are generated by `LightPipeline` instances.
"""


from collections import namedtuple
from typing import Generator, Optional, Sequence, Union

import numpy as np
from light_pipe_geo import raster_io, raster_trans, tiling
from osgeo import gdal

gdal.UseExceptions()


class LightPipeTile(namedtuple("LightPipeTile", ["X", "y", "band_map"])):
    """
    Contains sub-samples of raster data. Created by `LightPipeSample().tile()` 
    instance method.
    """
    def __new__(
        cls, X: np.ndarray, y: Optional[np.ndarray] = None, 
        band_map: Optional[dict] = None
    ):
        return tuple.__new__(cls, [X, y, band_map])


class SampleManifest(
    namedtuple("SampleManifest", 
        ["uid", "datasets", "labels", "metadata", "num_datasets"]
    )
):
    MANIFEST_SAMPLE_NUM: int = 0 # Used to make sample unique identifiers
    """
    Produced by `SampleMaker` instances and passed into `LightPipeSample` 
    instances as parameters. Used to structure data passing.
    """
    def __new__(
        cls, uid: Optional[Union[str, int]] = None, 
        datasets: Optional[Union[Sequence[gdal.Dataset], Sequence[gdal.Dataset]]] = None,
        labels: Optional[Union[Sequence[bool], bool]] = None,
        metadata: Optional[Union[Sequence[dict], dict]] = None,
        num_datasets: Optional[int] = None,
    ):
        if uid is None:
            uid = f"sample_{cls.MANIFEST_SAMPLE_NUM:05d}"
            cls.MANIFEST_SAMPLE_NUM += 1
        if isinstance(datasets, gdal.Dataset) or isinstance(datasets, str):
            datasets = [datasets]
        if isinstance(labels, bool):
            labels = [labels]
        elif labels is None:
            labels = [False for _ in range(len(datasets))]
        if isinstance(metadata, dict):
            metadata = [metadata]
        elif metadata is None:
            metadata = [dict() for _ in range(len(datasets))]
        if num_datasets is None:
            num_datasets = len(datasets)
        return tuple.__new__(cls, [uid, datasets, labels, metadata, num_datasets])

    
    def concatenate(self, manifests, uid: Optional[Union[int, str]] = None):
        if isinstance(manifests, gdal.Dataset) or isinstance(manifests, str):
            manifests = SampleManifest(datasets=manifests) # Don't use this if you can
        if isinstance(manifests, SampleManifest):
            manifests = [manifests]        
        datasets = self.datasets.copy()
        labels = self.labels.copy()
        metadata = self.metadata.copy()
        num_datasets = self.num_datasets
        for manifest in manifests:
            new_datasets = manifest.datasets
            new_labels = manifest.labels
            new_metadata = manifest.metadata
            new_num_datasets = manifest.num_datasets
            datasets += new_datasets
            labels += new_labels
            metadata += new_metadata
            num_datasets += new_num_datasets      
        new_manifest = SampleManifest(
            uid, datasets, labels, metadata, num_datasets
        )
        return new_manifest


class LightPipeSample:
    """
    Serves analysis-ready subsamples from arbitrarily-large raster(s) and 
    contains necessary variables and methods to format "predictions" into
    georeferenced files.
    """
    def __init__(
        self, data: Union[SampleManifest, gdal.Dataset, Sequence[gdal.Dataset]],
        preds: Optional[Sequence] = list(), pos_only: Optional[bool] = False, 
        non_null_only: Optional[bool] = False, tile_y: Optional[int] = 224, 
        tile_x: Optional[int] = 224, array_dtype = np.uint16, 
        row_major: Optional[bool] = False, tile_coords: Optional[Sequence] = None,
        shuffle_indices: Optional[Sequence] = None, *args, **kwargs
    ):
        # Create `SampleManifest` if not passed
        if not isinstance(data, SampleManifest):
            data = SampleManifest(datasets=data)
        self.data = data
        
        self.preds = preds
        self.pos_only = pos_only
        self.non_null_only = non_null_only
        self.tile_y = tile_y 
        self.tile_x = tile_x
        self.array_dtype = array_dtype 
        self.row_major = row_major
        self.tile_coords = tile_coords
        self.shuffle_indices = shuffle_indices
        self._i = 0


    def add_data(
        self, 
        data: Union[SampleManifest, gdal.Dataset, Sequence[gdal.Dataset]],
    ):
        if not isinstance(data, SampleManifest):
            data = SampleManifest(datasets=data)
        self.data = self.data.concatenate(data)
        return self


    def __iter__(self):
        return self


    def __next__(self):
        return self.next()


    def next(self):
        i = self._i
        n = self.data.num_datasets
        if i < n:
            self._i += 1
            dataset = self.data.datasets[i]
            if isinstance(dataset, str):
                dataset = gdal.Open(dataset)
            is_label = self.data.labels[i]
            metadata = self.data.metadata[i]
            return dataset, is_label, metadata
        raise StopIteration

    
    def shuffle(
        self, *args, **kwargs
    ) -> None:
        yield from self.tile(shuffle_tiles=True, *args, **kwargs)


    def unshuffle(
        self, preds: Optional[Union[Sequence, np.ndarray]] = None,
        shuffle_indices: Optional[np.ndarray] = None
    ):
        if preds is None:
            preds = self.preds
        assert preds is not None, \
            "`self.preds` instance variable must be set if `preds` not passed as parameter."
        if not isinstance(preds, np.ndarray):
            preds = np.array(preds)  
        if shuffle_indices is None and self.shuffle_indices is not None:
            shuffle_indices = self.shuffle_indices
        if shuffle_indices is not None:
            unshuffle_indices = np.zeros_like(shuffle_indices)
            unshuffle_indices[shuffle_indices] = np.arange(len(shuffle_indices))
            preds = preds[unshuffle_indices]
        return preds


    def tile(
        self, tile_y: Optional[int] = None, tile_x: Optional[int] = None, 
        array_dtype = None, row_major: Optional[bool] = None, 
        tile_coords = None, pos_only: Optional[bool] = None, 
        non_null_only: Optional[bool] = None, 
        shuffle_tiles: Optional[bool] = False, 
        assert_tile_smaller_than_raster: Optional[bool] = False,
        *args, **kwargs
    ) -> Generator:
        datasets = self.data.datasets
        labels = self.data.labels
        if tile_y is None:
            tile_y = self.tile_y
        else:
            self.tile_y = tile_y
        if tile_x is None:
            tile_x = self.tile_x
        else:
            self.tile_x = tile_x
        if array_dtype is None:
            array_dtype = self.array_dtype
        else:
            self.array_dtype = array_dtype
        if row_major is None:
            row_major = self.row_major
        else:
            self.row_major = row_major
        if tile_coords is None:
            tile_coords = self.tile_coords
        else:
            self.tile_coords = tile_coords
        if pos_only is None:
            pos_only = self.pos_only
        else:
            self.pos_only = pos_only
        if non_null_only is None:
            non_null_only = self.non_null_only
        else:
            self.non_null_only = non_null_only

        datasets, tiles, tile_coords, shuffle_indices, band_map = tiling.get_tiles(
            datasets=datasets, labels=labels, tile_y=tile_y, tile_x=tile_x, 
            array_dtype=array_dtype, row_major=row_major, tile_coords=tile_coords, 
            shuffle_tiles=shuffle_tiles, 
            assert_tile_smaller_than_raster=assert_tile_smaller_than_raster, 
            *args, **kwargs
        )
        self.tile_coords = tile_coords
        self.shuffle_indices = shuffle_indices
        self.band_map = band_map
        for tile_array in tiles:
            X = tile_array[band_map[False]]
            y = tile_array[band_map[True]]

            if pos_only and np.allclose(y, 0):
                continue
            if non_null_only and np.allclose(X, 0):
                continue

            tile = LightPipeTile(X=X, y=y, band_map=band_map)
            yield tile


    def load(self) -> None:
        for i in range(self.data.num_datasets):
            dataset = self.data.datasets[i]
            if isinstance(dataset, str):
                dataset = gdal.Open(dataset)
                self.data.datasets[i] = dataset


    def save(
        self, savepath: str, preds: Optional[Sequence] = None, *args, **kwargs
    ) -> None:
        """
        Saves predictions as files using the geospatial metadata associated
        with the `gdal.Dataset` instances in `self.datasets`. Delegates
        based on file extension of `savepath`.
        """
        if preds is None:
            preds = self.preds
            assert preds is not None, \
                "`self.preds` instance variable must be set if `preds` not passed as parameter."
        if not isinstance(preds, np.ndarray):
            preds = np.array(preds)            
        if raster_io.file_is_a(savepath, extension=".tif"):
            self._save_preds_as_geotiff(
                geotiff_path=savepath, preds=preds, *args, **kwargs
            )
        elif raster_io.file_is_a(savepath, extension=".csv"):
            self._save_preds_as_csv(
                geotiff_path=savepath, preds=preds, *args, **kwargs
            )
        else:
            raise NotImplementedError("`save` is not implemented for this file type.")
        

    def _save_preds_as_geotiff(
        self, geotiff_path: str, preds: np.ndarray, 
        tile_y: Optional[int] = None, tile_x: Optional[int] = None, 
        row_major: Optional[bool] = None, 
        use_ancestor_pixel_size: Optional[bool] = True, 
        pixel_x_size: Optional[Union[int, float]] = None,
        pixel_y_size: Optional[Union[int, float]] = None,
        n_bands: Optional[int] = 1, dtype = gdal.GDT_Byte,
        assert_north_up: Optional[bool] = True, *args, **kwargs
    ) -> None:
        if self.shuffle_indices is not None:
            preds = self.unshuffle(preds=preds)

        if tile_y is None:
            tile_y = self.tile_y
        if tile_x is None:
            tile_x = self.tile_x
        if row_major is None:
            row_major = self.row_major

        _, out_dataset = raster_trans.make_north_up_dataset_from_tiles_like(
            datasets=self.data.datasets, filepath=geotiff_path, tiles=preds,
            tile_y=tile_y, tile_x=tile_x, row_major=row_major, 
            use_ancestor_pixel_size=use_ancestor_pixel_size, 
            pixel_x_size=pixel_x_size, pixel_y_size=pixel_y_size, n_bands=n_bands,
            dtype=dtype, assert_north_up=assert_north_up, *args, **kwargs
        )
        return out_dataset


    def _save_preds_as_csv(
        self, geotiff_path: str, preds: np.ndarray, 
        tile_y: Optional[int] = None, tile_x: Optional[int] = None,
        *args, **kwargs
    ) -> None:
        # @TODO: IMPLEMENT THIS
        raise NotImplementedError
